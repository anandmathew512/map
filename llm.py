import json
import os

import httpx

LLM_BACKEND  = os.getenv("LLM_BACKEND", "ollama")   # "ollama" or "groq"
OLLAMA_BASE  = os.getenv("OLLAMA_BASE", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

_EXTRACT_SYSTEM = """You are a memory assistant. Given a piece of text, extract 3-8 atomic flashcards that capture the most important and non-obvious ideas.

Rules:
- Focus on insights worth remembering in 6 months, not surface facts
- Each card should prompt active recall (question / concept on front, explanation on back)
- Back: 1-3 sentences max, clear and specific
- Prefer "why" and "how" over "what"

Return ONLY a valid JSON array, no other text:
[{"front": "...", "back": "..."}, ...]"""

_CONNECTION_SYSTEM = """You are a memory assistant helping someone discover unexpected connections between ideas they've learned from different sources.

Given two flashcards, write 1-2 sentences describing a specific, non-obvious connection between them. Be concrete — name the shared principle, tension, or mechanism. Avoid generic phrases like "both relate to" or "similarly"."""


async def _via_groq(system: str, user: str, json_mode: bool = False) -> str:
    body: dict = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        "temperature": 0.3,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json=body,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def _via_ollama(system: str, prompt: str, json_mode: bool = False) -> str:
    body: dict = {
        "model": OLLAMA_MODEL,
        "system": system,
        "prompt": prompt,
        "stream": False,
    }
    if json_mode:
        body["format"] = "json"

    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(f"{OLLAMA_BASE}/api/generate", json=body)
        resp.raise_for_status()
        return resp.json()["response"].strip()


async def _generate(system: str, user: str, json_mode: bool = False) -> str:
    if LLM_BACKEND == "groq":
        return await _via_groq(system, user, json_mode)
    return await _via_ollama(system, user, json_mode)


async def extract_cards(content: str) -> list[dict]:
    raw = await _generate(
        _EXTRACT_SYSTEM,
        f"Text:\n\n{content[:5000]}",
        json_mode=True,
    )
    parsed = json.loads(raw)
    if isinstance(parsed, list):
        cards = parsed
    elif isinstance(parsed, dict):
        cards = next((v for v in parsed.values() if isinstance(v, list)), [])
    else:
        cards = []
    return [c for c in cards if isinstance(c, dict) and "front" in c and "back" in c]


async def synthesize_connection(card_a: dict, card_b: dict) -> str:
    prompt = (
        f"Card A:\nQ: {card_a['front']}\nA: {card_a['back']}\n\n"
        f"Card B (different source):\nQ: {card_b['front']}\nA: {card_b['back']}\n\n"
        "What's the specific, non-obvious connection?"
    )
    return await _generate(_CONNECTION_SYSTEM, prompt)
