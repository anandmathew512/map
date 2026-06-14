import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "memory.db"


def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sources (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            content     TEXT NOT NULL,
            source_type TEXT DEFAULT 'text',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS cards (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id   INTEGER REFERENCES sources(id) ON DELETE CASCADE,
            front       TEXT NOT NULL,
            back        TEXT NOT NULL,
            embedding   TEXT,
            ease_factor REAL    DEFAULT 2.5,
            interval    INTEGER DEFAULT 1,
            repetitions INTEGER DEFAULT 0,
            due_date    DATE    DEFAULT (date('now')),
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id     INTEGER REFERENCES cards(id) ON DELETE CASCADE,
            rating      INTEGER NOT NULL,
            reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()
