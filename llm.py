import json
import os

import httpx

OLLAMA_BASE = os.getenv("OLLAMA_BASE", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

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


async def extract_cards(content: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(
            f"{OLLAMA_BASE}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "system": _EXTRACT_SYSTEM,
                "prompt": f"Text:\n\n{content[:5000]}",
                "stream": False,
                "format": "json",
            },
        )
        resp.raise_for_status()
        raw = resp.json()["response"].strip()

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
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{OLLAMA_BASE}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "system": _CONNECTION_SYSTEM,
                "prompt": prompt,
                "stream": False,
            },
        )
        resp.raise_for_status()
        return resp.json()["response"].strip()
