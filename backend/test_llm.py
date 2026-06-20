import os
import httpx
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

print("=" * 50)

# Test Groq
if GROQ_API_KEY:
    try:
        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "user", "content": "Reply with exactly: GROQ WORKING"}
                ],
                "max_tokens": 20
            },
            timeout=20
        )

        print("Groq Status:", r.status_code)

        if r.status_code == 200:
            print("Groq Response:",
                  r.json()["choices"][0]["message"]["content"])
        else:
            print(r.text[:500])

    except Exception as e:
        print("Groq Error:", e)

print("=" * 50)

# Test Gemini
if GEMINI_API_KEY:
    try:
        r = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}",
            json={
                "contents": [
                    {
                        "parts": [
                            {"text": "Reply with exactly: GEMINI WORKING"}
                        ]
                    }
                ]
            },
            timeout=20
        )

        print("Gemini Status:", r.status_code)

        if r.status_code == 200:
            print(
                "Gemini Response:",
                r.json()["candidates"][0]["content"]["parts"][0]["text"]
            )
        else:
            print(r.text[:500])

    except Exception as e:
        print("Gemini Error:", e)

print("=" * 50)

# Test OpenAI
if OPENAI_API_KEY:
    try:
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}"
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "user", "content": "Reply with exactly: OPENAI WORKING"}
                ],
                "max_tokens": 20
            },
            timeout=20
        )

        print("OpenAI Status:", r.status_code)

        if r.status_code == 200:
            print(
                "OpenAI Response:",
                r.json()["choices"][0]["message"]["content"]
            )
        else:
            print(r.text[:500])

    except Exception as e:
        print("OpenAI Error:", e)

print("=" * 50)