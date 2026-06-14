import json
from functools import lru_cache

import numpy as np


@lru_cache(maxsize=1)
def _get_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("all-MiniLM-L6-v2")


def embed(text: str) -> list[float]:
    model = _get_model()
    vec = model.encode(text, normalize_embeddings=True)
    return vec.tolist()


def _cosine(a: list[float], b: list[float]) -> float:
    return float(np.dot(np.array(a), np.array(b)))  # pre-normalized


def find_similar(
    query_embedding: list[float],
    candidates: list[dict],
    top_k: int = 3,
    exclude_source_id: int | None = None,
) -> list[dict]:
    scored = []
    for c in candidates:
        if not c.get("embedding"):
            continue
        if exclude_source_id is not None and c.get("source_id") == exclude_source_id:
            continue
        emb = json.loads(c["embedding"]) if isinstance(c["embedding"], str) else c["embedding"]
        scored.append({**c, "similarity": _cosine(query_embedding, emb)})

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:top_k]
