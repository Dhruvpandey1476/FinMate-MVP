"""
LLM Client — Multi-provider AI backbone for FinMate.

Provider priority: Groq → Gemini → OpenAI → rule-based fallback.
Each provider is tried in order; if one fails, the next is used.
The rule-based fallback is LAST RESORT only (not default like before).

Groq:   llama-3.3-70b-versatile  (fast, free tier generous)
Gemini: gemini-2.5-pro           (high quality, free tier)
OpenAI: gpt-4o-mini              (reliable, paid)
"""
import os
import json
import logging
from typing import Optional

from sentence_transformers import SentenceTransformer

_model = SentenceTransformer(
    "sentence-transformers/all-MiniLM-L6-v2"
)
EMBEDDING_DIM = 384
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger("finmate.llm")

# ─── Config ──────────────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")

# Track which provider actually responded (for UI status)
_last_provider_used: str = "none"


def get_last_provider() -> str:
    return _last_provider_used


def generate(prompt: str, fallback: str = "", system_prompt: str = "", temperature: float = 0.7) -> str:
    """
    Generate text using the best available LLM provider.
    
    Unlike the old version, the LLM is the PRIMARY path.
    The rule-based `fallback` is only used if ALL providers fail.
    """
    global _last_provider_used
    
    providers = _get_provider_chain()
    
    for provider_name, provider_fn in providers:
        try:
            result = provider_fn(prompt, system_prompt, temperature)
            if result and result.strip():
                _last_provider_used = provider_name
                logger.info("LLM response from %s (%d chars)", provider_name, len(result))
                return result.strip()
        except Exception as e:
            logger.warning("Provider %s failed: %s — trying next.", provider_name, str(e)[:100])
            continue
    
    # All providers failed
    _last_provider_used = "rule_based"
    logger.warning("All LLM providers failed. Using rule-based fallback.")
    return fallback if fallback else "I'm having trouble connecting to the AI service. Please try again shortly."


def generate_json(prompt: str, system_prompt: str = "", fallback: Optional[dict] = None) -> dict:
    """Generate structured JSON output from LLM."""
    full_prompt = prompt + "\n\nIMPORTANT: Respond with valid JSON only. No markdown, no code fences, no explanation."
    result = generate(full_prompt, fallback=json.dumps(fallback or {}), system_prompt=system_prompt, temperature=0.3)
    
    # Try to parse JSON from the response
    try:
        # Strip markdown code fences if present
        cleaned = result.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
        return json.loads(cleaned)
    except (json.JSONDecodeError, IndexError):
        logger.warning("Failed to parse LLM JSON output, using fallback")
        return fallback or {}


def _get_provider_chain():
    """Build ordered provider chain based on config and available keys."""
    chain = []
    
    # Primary provider first
    if LLM_PROVIDER == "groq" and GROQ_API_KEY and GROQ_API_KEY != "YOUR_GROQ_API_KEY_HERE":
        chain.append(("groq", _call_groq))
    if LLM_PROVIDER == "gemini" and GEMINI_API_KEY:
        chain.append(("gemini", _call_gemini))
    if LLM_PROVIDER == "openai" and OPENAI_API_KEY:
        chain.append(("openai", _call_openai))
    
    # Then fallbacks (all providers not already in the chain)
    if ("groq", _call_groq) not in chain and GROQ_API_KEY and GROQ_API_KEY != "YOUR_GROQ_API_KEY_HERE":
        chain.append(("groq", _call_groq))
    if ("gemini", _call_gemini) not in chain and GEMINI_API_KEY:
        chain.append(("gemini", _call_gemini))
    if ("openai", _call_openai) not in chain and OPENAI_API_KEY:
        chain.append(("openai", _call_openai))
    
    return chain


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=4), 
       retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)))
def _call_groq(prompt: str, system_prompt: str = "", temperature: float = 0.7) -> str:
    """Call Groq API (llama-3.3-70b-versatile)."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    resp = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": GROQ_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 2048,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=4),
       retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)))
def _call_gemini(prompt: str, system_prompt: str = "", temperature: float = 0.7) -> str:
    """Call Gemini API."""
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    )
    
    contents = []
    if system_prompt:
        contents.append({"role": "user", "parts": [{"text": system_prompt}]})
        contents.append({"role": "model", "parts": [{"text": "Understood. I will follow these instructions."}]})
    contents.append({"role": "user", "parts": [{"text": prompt}]})
    
    resp = httpx.post(
        url,
        json={
            "contents": contents,
            "generationConfig": {"temperature": temperature, "maxOutputTokens": 2048},
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=4),
       retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)))
def _call_openai(prompt: str, system_prompt: str = "", temperature: float = 0.7) -> str:
    """Call OpenAI API (gpt-4o-mini)."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    resp = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        json={
            "model": "gpt-4o-mini",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 2048,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


# ─── Embeddings (Gemini text-embedding-004) ──────────────────────────────────

def get_embedding(text:str):
    return _model.encode(text).tolist()
