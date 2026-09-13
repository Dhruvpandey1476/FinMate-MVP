"""
LLM Client - multi-provider AI backbone for FinMate.

Provider priority: Groq -> Gemini -> OpenAI -> rule-based fallback.
Each provider is tried in order; if one fails, the next is used.
The rule-based fallback is LAST RESORT only.

Groq:   openai/gpt-oss-120b   (fast, generous free tier)
Gemini: gemini-flash-latest   (tracks the current Flash release)
OpenAI: gpt-4o-mini           (reliable, paid)

Model ids are pinned in env vars because providers decommission them without
notice - llama-3.3-70b-versatile and gemini-2.0-flash both started returning
404 while still hardcoded here, and the app silently served rule-based replies.
Note that gpt-oss is a reasoning model: leave max_tokens generous or the
reasoning pass consumes the whole budget and content comes back empty.

Every call returns token counts alongside the text so the caller can meter cost
(see services/entitlements.py). `generate()` keeps the old string-returning
signature; `generate_detailed()` exposes the full result.
"""
import os
import json
import time
import logging
from dataclasses import dataclass, field
from typing import Optional, Iterator

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger("finmate.llm")

EMBEDDING_DIM = 384
_embed_model = None  # lazily loaded - keeps cold starts fast and deps optional

# --- Config ----------------------------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "30"))

_PLACEHOLDER_KEYS = {"", "YOUR_GROQ_API_KEY_HERE", "YOUR_API_KEY_HERE", "changeme"}

# Track which provider actually responded (for UI status)
_last_provider_used: str = "none"


@dataclass
class LLMResult:
    """Outcome of a generation attempt, including what it cost."""
    text: str = ""
    provider: str = "none"
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    ok: bool = False
    errors: list = field(default_factory=list)



def _describe_error(exc: Exception) -> str:
    """
    Turn a provider exception into something a human can act on.

    tenacity wraps failures in RetryError, whose repr is
    "RetryError[<Future at 0x... state=finished raised HTTPStatusError>]" - it
    hides the status code and the body, which is exactly the information needed
    to tell a dead model id from a bad key from a rate limit.
    """
    from tenacity import RetryError

    if isinstance(exc, RetryError):
        try:
            inner = exc.last_attempt.exception()
            if inner is not None:
                exc = inner
        except Exception:
            pass

    if isinstance(exc, httpx.HTTPStatusError):
        body = ""
        try:
            body = exc.response.text[:200]
        except Exception:
            pass
        return f"HTTP {exc.response.status_code} {body}".strip()

    if isinstance(exc, httpx.TimeoutException):
        return f"timeout after {LLM_TIMEOUT}s"

    return f"{type(exc).__name__}: {str(exc)[:160]}"


def get_last_provider() -> str:
    return _last_provider_used


def _key_ok(key: str) -> bool:
    return bool(key) and key not in _PLACEHOLDER_KEYS


def llm_configured() -> bool:
    return _key_ok(GROQ_API_KEY) or _key_ok(GEMINI_API_KEY) or _key_ok(OPENAI_API_KEY)


def _estimate_tokens(text: str) -> int:
    """~4 chars per token. Only used when a provider omits usage data."""
    return max(1, len(text or "") // 4)


def generate_detailed(
    prompt: str,
    fallback: str = "",
    system_prompt: str = "",
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> LLMResult:
    """Generate text, returning provider/token metadata for metering."""
    global _last_provider_used

    started = time.monotonic()
    errors = []

    for provider_name, provider_fn, model_name in _get_provider_chain():
        try:
            text, ptok, ctok = provider_fn(prompt, system_prompt, temperature, max_tokens)
            if text and text.strip():
                _last_provider_used = provider_name
                elapsed = int((time.monotonic() - started) * 1000)
                logger.info(
                    "LLM response from %s (%d chars, %d+%d tokens, %dms)",
                    provider_name, len(text), ptok, ctok, elapsed,
                )
                return LLMResult(
                    text=text.strip(),
                    provider=provider_name,
                    model=model_name,
                    prompt_tokens=ptok,
                    completion_tokens=ctok,
                    latency_ms=elapsed,
                    ok=True,
                    errors=errors,
                )
        except Exception as e:
            detail = _describe_error(e)
            errors.append(f"{provider_name}: {detail}")
            logger.warning("Provider %s failed: %s - trying next.", provider_name, detail)
            continue

    _last_provider_used = "rule_based"
    logger.warning("All LLM providers failed. Using rule-based fallback.")
    return LLMResult(
        text=fallback or "I'm having trouble reaching the AI service right now. Please try again shortly.",
        provider="rule_based",
        model="",
        latency_ms=int((time.monotonic() - started) * 1000),
        ok=False,
        errors=errors,
    )


def generate(prompt: str, fallback: str = "", system_prompt: str = "", temperature: float = 0.7) -> str:
    """String-returning wrapper kept for existing call sites."""
    return generate_detailed(prompt, fallback, system_prompt, temperature).text


def generate_json(prompt: str, system_prompt: str = "", fallback=None):
    """Generate structured JSON output from an LLM."""
    full_prompt = prompt + "\n\nIMPORTANT: Respond with valid JSON only. No markdown, no code fences, no explanation."
    result = generate_detailed(
        full_prompt,
        fallback=json.dumps(fallback if fallback is not None else {}),
        system_prompt=system_prompt,
        temperature=0.3,
    )
    return _parse_json(result.text, fallback)


def _parse_json(raw: str, fallback=None):
    try:
        cleaned = (raw or "").strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
        return json.loads(cleaned)
    except (json.JSONDecodeError, IndexError, AttributeError):
        logger.warning("Failed to parse LLM JSON output, using fallback")
        return fallback if fallback is not None else {}


def _get_provider_chain():
    """Ordered (name, fn, model) tuples: configured provider first, then the rest."""
    available = []
    if _key_ok(GROQ_API_KEY):
        available.append(("groq", _call_groq, GROQ_MODEL))
    if _key_ok(GEMINI_API_KEY):
        available.append(("gemini", _call_gemini, GEMINI_MODEL))
    if _key_ok(OPENAI_API_KEY):
        available.append(("openai", _call_openai, OPENAI_MODEL))

    available.sort(key=lambda p: 0 if p[0] == LLM_PROVIDER else 1)
    return available


# --- Providers -------------------------------------------------------------
# Each returns (text, prompt_tokens, completion_tokens).

_RETRY = dict(
    stop=stop_after_attempt(2),
    wait=wait_exponential(min=1, max=4),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
)


def _openai_style_usage(data, prompt: str, text: str):
    usage = data.get("usage") or {}
    return (
        int(usage.get("prompt_tokens") or _estimate_tokens(prompt)),
        int(usage.get("completion_tokens") or _estimate_tokens(text)),
    )


@retry(**_RETRY)
def _call_groq(prompt: str, system_prompt: str = "", temperature: float = 0.7, max_tokens: int = 2048):
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    resp = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={"model": GROQ_MODEL, "messages": messages,
              "temperature": temperature, "max_tokens": max_tokens},
        timeout=LLM_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    text = data["choices"][0]["message"]["content"]
    ptok, ctok = _openai_style_usage(data, prompt, text)
    return text, ptok, ctok


@retry(**_RETRY)
def _call_gemini(prompt: str, system_prompt: str = "", temperature: float = 0.7, max_tokens: int = 2048):
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
    }
    # Gemini has a first-class system instruction slot; using it keeps the
    # system prompt out of the conversation turns where a user message could
    # more easily talk over it.
    if system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

    resp = httpx.post(url, json=payload, timeout=LLM_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    usage = data.get("usageMetadata") or {}
    ptok = int(usage.get("promptTokenCount") or _estimate_tokens(prompt))
    ctok = int(usage.get("candidatesTokenCount") or _estimate_tokens(text))
    return text, ptok, ctok


@retry(**_RETRY)
def _call_openai(prompt: str, system_prompt: str = "", temperature: float = 0.7, max_tokens: int = 2048):
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    resp = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
        json={"model": OPENAI_MODEL, "messages": messages,
              "temperature": temperature, "max_tokens": max_tokens},
        timeout=LLM_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    text = data["choices"][0]["message"]["content"]
    ptok, ctok = _openai_style_usage(data, prompt, text)
    return text, ptok, ctok


# --- Streaming -------------------------------------------------------------

def stream(
    prompt: str,
    fallback: str = "",
    system_prompt: str = "",
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> Iterator[dict]:
    """
    Yield incremental chunks: {"type": "token", "text": ...} then a final
    {"type": "done", "result": LLMResult}.

    Falls back to non-streaming providers, and finally to the rule-based text,
    so the caller can always render something.
    """
    started = time.monotonic()
    errors = []

    for provider_name, _fn, model_name in _get_provider_chain():
        streamer = _STREAMERS.get(provider_name)
        if not streamer:
            continue
        try:
            collected = []
            for token in streamer(prompt, system_prompt, temperature, max_tokens):
                collected.append(token)
                yield {"type": "token", "text": token}
            text = "".join(collected).strip()
            if text:
                global _last_provider_used
                _last_provider_used = provider_name
                yield {
                    "type": "done",
                    "result": LLMResult(
                        text=text,
                        provider=provider_name,
                        model=model_name,
                        prompt_tokens=_estimate_tokens(prompt + system_prompt),
                        completion_tokens=_estimate_tokens(text),
                        latency_ms=int((time.monotonic() - started) * 1000),
                        ok=True,
                        errors=errors,
                    ),
                }
                return
        except Exception as e:
            detail = _describe_error(e)
            errors.append(f"{provider_name}: {detail}")
            logger.warning("Streaming provider %s failed: %s", provider_name, detail)
            continue

    # No streaming provider worked - fall back to a single blocking call.
    result = generate_detailed(prompt, fallback, system_prompt, temperature, max_tokens)
    result.errors = errors + list(result.errors or [])
    if result.text:
        yield {"type": "token", "text": result.text}
    yield {"type": "done", "result": result}


def _stream_openai_style(url: str, headers: dict, model: str,
                         prompt: str, system_prompt: str, temperature: float, max_tokens: int):
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    with httpx.stream(
        "POST", url, headers=headers,
        json={"model": model, "messages": messages, "temperature": temperature,
              "max_tokens": max_tokens, "stream": True},
        timeout=LLM_TIMEOUT,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
                delta = chunk["choices"][0]["delta"].get("content")
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            if delta:
                yield delta


def _stream_groq(prompt, system_prompt, temperature, max_tokens):
    yield from _stream_openai_style(
        "https://api.groq.com/openai/v1/chat/completions",
        {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        GROQ_MODEL, prompt, system_prompt, temperature, max_tokens,
    )


def _stream_openai(prompt, system_prompt, temperature, max_tokens):
    yield from _stream_openai_style(
        "https://api.openai.com/v1/chat/completions",
        {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
        OPENAI_MODEL, prompt, system_prompt, temperature, max_tokens,
    )


def _stream_gemini(prompt, system_prompt, temperature, max_tokens):
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:streamGenerateContent?alt=sse&key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
    }
    if system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

    with httpx.stream("POST", url, json=payload, timeout=LLM_TIMEOUT) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            try:
                chunk = json.loads(line[5:].strip())
                delta = chunk["candidates"][0]["content"]["parts"][0]["text"]
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            if delta:
                yield delta


_STREAMERS = {
    "groq": _stream_groq,
    "gemini": _stream_gemini,
    "openai": _stream_openai,
}


# --- Embeddings (local MiniLM, lazily loaded) ------------------------------

def get_embedding(text: str):
    """
    Return a 384-dim embedding, or None if sentence-transformers isn't installed.
    Loaded lazily so the app boots (and deploys) without the heavy torch stack -
    when embeddings are unavailable, the memory engine uses keyword search.
    """
    global _embed_model
    if _embed_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embed_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        except Exception as e:
            logger.warning("Embeddings unavailable (%s) - using keyword memory search.", e)
            return None
    try:
        return _embed_model.encode(text).tolist()
    except Exception:
        return None
