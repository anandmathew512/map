import asyncio
import json
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from database import get_db, init_db
from embeddings import embed, find_similar
from llm import extract_cards as llm_extract, synthesize_connection
from sm2 import calculate_next_review

STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)


# ── Pydantic models ────────────────────────────────────────────────────────────

class IngestPreviewReq(BaseModel):
    content: str
    title: str
    source_type: str = "text"


class IngestSaveReq(BaseModel):
    content: str
    title: str
    source_type: str = "text"
    cards: list[dict]


class ReviewRatingReq(BaseModel):
    rating: int  # 1-4


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/api/stats")
def get_stats():
    conn = get_db()
    today = str(date.today())
    total = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
    due = conn.execute(
        "SELECT COUNT(*) FROM cards WHERE due_date <= ?", (today,)
    ).fetchone()[0]
    sources = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    conn.close()
    return {"total_cards": total, "due_today": due, "total_sources": sources}


@app.post("/api/ingest/preview")
async def ingest_preview(req: IngestPreviewReq):
    content = req.content

    if req.source_type == "url":
        try:
            import httpx as _httpx
            async with _httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(req.content)
                html = resp.text
            try:
                import trafilatura
                content = trafilatura.extract(html) or html[:4000]
            except Exception:
                import re
                content = re.sub(r"<[^>]+>", " ", html)[:4000]
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not fetch URL: {e}")

    try:
        cards = await llm_extract(content)
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"LLM failed — is Ollama running with '{__import__('os').getenv('OLLAMA_MODEL','llama3.2')}'? Error: {e}",
        )

    if not cards:
        raise HTTPException(status_code=422, detail="Model returned no cards. Try different content.")

    return {"cards": cards, "content": content}


@app.post("/api/ingest/save")
async def ingest_save(req: IngestSaveReq):
    loop = asyncio.get_event_loop()

    cards_with_emb = []
    for card in req.cards:
        emb = await loop.run_in_executor(None, embed, f"{card['front']} {card['back']}")
        cards_with_emb.append({**card, "embedding": json.dumps(emb)})

    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO sources (title, content, source_type) VALUES (?,?,?)",
            (req.title, req.content, req.source_type),
        )
        source_id = cur.lastrowid
        for card in cards_with_emb:
            conn.execute(
                "INSERT INTO cards (source_id, front, back, embedding) VALUES (?,?,?,?)",
                (source_id, card["front"], card["back"], card["embedding"]),
            )
        conn.commit()
    finally:
        conn.close()

    return {"source_id": source_id, "saved_cards": len(cards_with_emb)}


@app.get("/api/review/next")
def review_next():
    conn = get_db()
    today = str(date.today())
    row = conn.execute(
        """SELECT c.*, s.title AS source_title
           FROM cards c LEFT JOIN sources s ON s.id = c.source_id
           WHERE c.due_date <= ?
           ORDER BY c.due_date ASC, c.id ASC
           LIMIT 1""",
        (today,),
    ).fetchone()
    if not row:
        conn.close()
        return {"card": None, "due_count": 0}
    due_count = conn.execute(
        "SELECT COUNT(*) FROM cards WHERE due_date <= ?", (today,)
    ).fetchone()[0]
    conn.close()
    return {"card": dict(row), "due_count": due_count}


@app.post("/api/review/{card_id}")
async def submit_review(card_id: int, req: ReviewRatingReq):
    if req.rating not in (1, 2, 3, 4):
        raise HTTPException(status_code=400, detail="Rating must be 1-4")

    conn = get_db()
    row = conn.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Card not found")
    card = dict(row)

    new_ef, new_iv, new_reps, new_due = calculate_next_review(
        req.rating, card["ease_factor"], card["interval"], card["repetitions"]
    )
    conn.execute(
        "UPDATE cards SET ease_factor=?,interval=?,repetitions=?,due_date=? WHERE id=?",
        (new_ef, new_iv, new_reps, str(new_due), card_id),
    )
    conn.execute("INSERT INTO reviews (card_id,rating) VALUES (?,?)", (card_id, req.rating))
    conn.commit()

    connections = []
    if card.get("embedding"):
        query_emb = json.loads(card["embedding"])
        candidates = [
            dict(r)
            for r in conn.execute(
                "SELECT id,source_id,front,back,embedding FROM cards WHERE id!=? AND embedding IS NOT NULL",
                (card_id,),
            ).fetchall()
        ]
        similar = find_similar(query_emb, candidates, top_k=3, exclude_source_id=card["source_id"])

        for i, s in enumerate(similar):
            insight = None
            if i == 0:
                try:
                    insight = await synthesize_connection(card, s)
                except Exception:
                    pass
            connections.append({
                "card": {k: v for k, v in s.items() if k != "embedding"},
                "insight": insight,
                "similarity": round(s["similarity"], 3),
            })

    conn.close()
    return {"next_due": str(new_due), "new_interval": new_iv, "connections": connections}


@app.get("/api/cards")
def list_cards(offset: int = 0, limit: int = 100):
    conn = get_db()
    rows = conn.execute(
        """SELECT c.id, c.front, c.back, c.due_date, c.interval, c.repetitions,
                  c.ease_factor, c.created_at, s.title AS source_title, c.source_id
           FROM cards c LEFT JOIN sources s ON s.id = c.source_id
           ORDER BY c.created_at DESC LIMIT ? OFFSET ?""",
        (limit, offset),
    ).fetchall()
    total = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
    conn.close()
    return {"cards": [dict(r) for r in rows], "total": total}


@app.delete("/api/cards/{card_id}")
def delete_card(card_id: int):
    conn = get_db()
    conn.execute("DELETE FROM cards WHERE id=?", (card_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/sources")
def list_sources():
    conn = get_db()
    rows = conn.execute(
        """SELECT s.*, COUNT(c.id) AS card_count
           FROM sources s LEFT JOIN cards c ON c.source_id = s.id
           GROUP BY s.id ORDER BY s.created_at DESC""",
    ).fetchall()
    conn.close()
    return {"sources": [dict(r) for r in rows]}


# ── Static files & SPA fallback ────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    return FileResponse(str(STATIC / "index.html"))
