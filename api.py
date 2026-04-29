import os, threading
from datetime import datetime
from typing import Optional

import pytz
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

CHILE_TZ    = pytz.timezone("America/Santiago")
DATABASE_URL = os.environ.get("DATABASE_URL", "")  # Railway lo inyecta automáticamente
USE_PG      = bool(DATABASE_URL)
_lock       = threading.Lock()

# ── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(title="HotBoat Tracker")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# ── DB helpers (Postgres en Railway, SQLite en local) ────────────────────────
if USE_PG:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    def _get_conn():
        url = DATABASE_URL
        # Railway usa postgres:// pero psycopg2 necesita postgresql://
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return psycopg2.connect(url, cursor_factory=RealDictCursor)

    def _init_db():
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS visitor_events (
                        id           SERIAL PRIMARY KEY,
                        session_id   TEXT    NOT NULL,
                        event_type   TEXT    NOT NULL,
                        extra        TEXT,
                        lang         TEXT,
                        referrer     TEXT,
                        is_returning BOOLEAN DEFAULT FALSE,
                        recorded_at  TIMESTAMPTZ NOT NULL
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_ve_sid  ON visitor_events(session_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_ve_evt  ON visitor_events(event_type)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_ve_ts   ON visitor_events(recorded_at)")
            conn.commit()

    def _insert(sid, event, extra, lang, referrer, returning, now):
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO visitor_events
                       (session_id, event_type, extra, lang, referrer, is_returning, recorded_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (sid, event, extra, lang, referrer, returning, now),
                )
            conn.commit()

    def _query(sql, params=()):
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()

else:
    import sqlite3
    DB_PATH = os.path.join(os.path.dirname(__file__), "visitor_events.db")

    def _init_db():
        with sqlite3.connect(DB_PATH) as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS visitor_events (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id   TEXT    NOT NULL,
                    event_type   TEXT    NOT NULL,
                    extra        TEXT,
                    lang         TEXT,
                    referrer     TEXT,
                    is_returning INTEGER DEFAULT 0,
                    recorded_at  TEXT    NOT NULL
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_sid ON visitor_events(session_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_evt ON visitor_events(event_type)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_ts  ON visitor_events(recorded_at)")
            c.commit()

    def _insert(sid, event, extra, lang, referrer, returning, now):
        with sqlite3.connect(DB_PATH) as c:
            c.execute(
                """INSERT INTO visitor_events
                   (session_id, event_type, extra, lang, referrer, is_returning, recorded_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (sid, event, extra, lang, referrer, int(returning), now),
            )
            c.commit()

    def _query(sql, params=()):
        with sqlite3.connect(DB_PATH) as c:
            return c.execute(sql, params).fetchall()

_init_db()

# ── Modelos ───────────────────────────────────────────────────────────────────
class TrackRequest(BaseModel):
    event:        str
    session_id:   str
    extra:        Optional[str]  = None
    lang:         Optional[str]  = "es-CL"
    referrer:     Optional[str]  = ""
    is_returning: Optional[bool] = False

# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.post("/api/track")
def track(body: TrackRequest):
    sid   = (body.session_id or "").strip()[:64]
    event = (body.event      or "").strip()[:64]
    if not sid or not event:
        return {"ok": False}
    now = datetime.now(CHILE_TZ).isoformat()
    with _lock:
        _insert(
            sid, event, body.extra,
            (body.lang     or "")[:16],
            (body.referrer or "")[:200],
            body.is_returning, now,
        )
    return {"ok": True}


@app.get("/api/stats")
def stats(days: int = 30):
    if USE_PG:
        cutoff_expr = f"NOW() - INTERVAL '{days} days'"
        sql_filter  = f"recorded_at >= {cutoff_expr}"
    else:
        sql_filter  = f"recorded_at >= datetime('now', '-{days} days')"

    visits = _query(
        f"SELECT COUNT(DISTINCT session_id) FROM visitor_events "
        f"WHERE event_type='page_visit' AND {sql_filter}"
    )[0][0]

    funnel = _query(
        f"""SELECT event_type, COUNT(*) AS hits, COUNT(DISTINCT session_id) AS sessions
            FROM visitor_events WHERE {sql_filter}
            GROUP BY event_type ORDER BY hits DESC"""
    )

    by_lang = _query(
        f"""SELECT lang, COUNT(DISTINCT session_id) AS sessions
            FROM visitor_events WHERE event_type='page_visit' AND {sql_filter}
            GROUP BY lang ORDER BY sessions DESC"""
    )

    returning = _query(
        f"""SELECT is_returning, COUNT(DISTINCT session_id)
            FROM visitor_events WHERE event_type='page_visit' AND {sql_filter}
            GROUP BY is_returning"""
    )

    def row(r): return list(r.values()) if isinstance(r, dict) else list(r)

    return {
        "days":         days,
        "total_visits": visits,
        "funnel":       [{"event": row(r)[0], "hits": row(r)[1], "sessions": row(r)[2]} for r in funnel],
        "by_lang":      [{"lang": row(r)[0], "sessions": row(r)[1]} for r in by_lang],
        "returning":    {("returning" if row(r)[0] else "new"): row(r)[1] for r in returning},
    }


@app.get("/api/session/{sid}")
def session_detail(sid: str):
    if USE_PG:
        rows = _query(
            "SELECT event_type, extra, lang, recorded_at FROM visitor_events "
            "WHERE session_id=%s ORDER BY recorded_at ASC", (sid[:64],)
        )
    else:
        rows = _query(
            "SELECT event_type, extra, lang, recorded_at FROM visitor_events "
            "WHERE session_id=? ORDER BY recorded_at ASC", (sid[:64],)
        )

    def row(r): return list(r.values()) if isinstance(r, dict) else list(r)
    return {"session_id": sid, "events": [
        {"event": row(r)[0], "extra": row(r)[1], "lang": row(r)[2], "at": str(row(r)[3])} for r in rows
    ]}


# ── Sirve la landing ──────────────────────────────────────────────────────────
app.mount("/", StaticFiles(directory=os.path.dirname(__file__) or ".", html=True), name="static")
