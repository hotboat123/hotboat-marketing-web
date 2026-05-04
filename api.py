import os, threading
from datetime import datetime
from pathlib import Path
from typing import Optional

import pytz
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from meta_pixel import (
    apply_meta_pixel_placeholder,
    get_meta_pixel_id,
    meta_pixel_startup_message,
)

_ROOT_DIR = Path(__file__).resolve().parent
_INDEX_PATH = _ROOT_DIR / "index.html"
_META_PIXEL_ID = get_meta_pixel_id()
print(meta_pixel_startup_message(), flush=True)

CHILE_TZ     = pytz.timezone("America/Santiago")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_PG       = bool(DATABASE_URL)
_lock        = threading.Lock()

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="HotBoat Tracker")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# ── DB helpers ────────────────────────────────────────────────────────────────
if USE_PG:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    def _get_conn():
        url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        return psycopg2.connect(url, cursor_factory=RealDictCursor)

    def _init_db():
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS booking_visitor_events (
                        id           SERIAL PRIMARY KEY,
                        session_id   VARCHAR(64)  NOT NULL,
                        event_type   VARCHAR(96)  NOT NULL,
                        extra_date   TEXT,
                        time_label   VARCHAR(16),
                        lang         VARCHAR(8)   DEFAULT 'es',
                        referrer     TEXT         DEFAULT '',
                        is_returning BOOLEAN      DEFAULT FALSE,
                        recorded_at  TIMESTAMPTZ  DEFAULT NOW()
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_bve_sid ON booking_visitor_events(session_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_bve_ts  ON booking_visitor_events(recorded_at)")
            conn.commit()

    def _insert(sid, event, extra, lang, referrer, returning, now, time_label):
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO booking_visitor_events
                       (session_id, event_type, extra_date, time_label, lang, referrer, is_returning, recorded_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (sid, event, extra, time_label, lang, referrer, returning, now),
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
                CREATE TABLE IF NOT EXISTS booking_visitor_events (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id   TEXT    NOT NULL,
                    event_type   TEXT    NOT NULL,
                    extra_date   TEXT,
                    time_label   TEXT,
                    lang         TEXT    DEFAULT 'es',
                    referrer     TEXT    DEFAULT '',
                    is_returning INTEGER DEFAULT 0,
                    recorded_at  TEXT    NOT NULL
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_bve_sid ON booking_visitor_events(session_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_bve_ts  ON booking_visitor_events(recorded_at)")
            c.commit()

    def _insert(sid, event, extra, lang, referrer, returning, now, time_label):
        with sqlite3.connect(DB_PATH) as c:
            c.execute(
                """INSERT INTO booking_visitor_events
                   (session_id, event_type, extra_date, time_label, lang, referrer, is_returning, recorded_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (sid, event, extra, time_label, lang, referrer, int(returning), now),
            )
            c.commit()

    def _query(sql, params=()):
        with sqlite3.connect(DB_PATH) as c:
            return c.execute(sql, params).fetchall()

_init_db()
print(f"[DB] Using {'PostgreSQL' if USE_PG else 'SQLite (no DATABASE_URL found)'}", flush=True)

# ── Modelos ───────────────────────────────────────────────────────────────────
class TrackRequest(BaseModel):
    event:        str
    session_id:   str
    extra:        Optional[str]  = None
    lang:         Optional[str]  = "es"
    referrer:     Optional[str]  = ""
    is_returning: Optional[bool] = False

# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.post("/api/track")
def track(body: TrackRequest):
    sid   = (body.session_id or "").strip()[:64]
    event = (body.event      or "").strip()[:96]
    if not sid or not event:
        return {"ok": False}
    now        = datetime.now(CHILE_TZ)
    time_label = now.strftime("%H:%M")
    try:
        with _lock:
            _insert(
                sid, event, body.extra,
                (body.lang     or "es")[:8],
                (body.referrer or "")[:200],
                body.is_returning,
                now.isoformat(),
                time_label,
            )
    except Exception as e:
        print(f"[TRACK ERROR] {e}", flush=True)
        return {"ok": False, "error": str(e)}
    return {"ok": True}


@app.get("/api/stats")
def stats(days: int = 30):
    if USE_PG:
        f = f"recorded_at >= NOW() - INTERVAL '{days} days'"
    else:
        f = f"recorded_at >= datetime('now', '-{days} days')"

    def row(r): return list(r.values()) if isinstance(r, dict) else list(r)

    visits = row(_query(
        f"SELECT COUNT(DISTINCT session_id) FROM booking_visitor_events "
        f"WHERE event_type='page_visit' AND {f}"
    )[0])[0]

    funnel = _query(
        f"SELECT event_type, COUNT(*) AS hits, COUNT(DISTINCT session_id) AS sessions "
        f"FROM booking_visitor_events WHERE {f} "
        f"GROUP BY event_type ORDER BY hits DESC"
    )

    by_lang = _query(
        f"SELECT lang, COUNT(DISTINCT session_id) AS sessions "
        f"FROM booking_visitor_events WHERE event_type='page_visit' AND {f} "
        f"GROUP BY lang ORDER BY sessions DESC"
    )

    returning = _query(
        f"SELECT is_returning, COUNT(DISTINCT session_id) "
        f"FROM booking_visitor_events WHERE event_type='page_visit' AND {f} "
        f"GROUP BY is_returning"
    )

    return {
        "days":         days,
        "total_visits": visits,
        "funnel":       [{"event": row(r)[0], "hits": row(r)[1], "sessions": row(r)[2]} for r in funnel],
        "by_lang":      [{"lang": row(r)[0], "sessions": row(r)[1]} for r in by_lang],
        "returning":    {("returning" if row(r)[0] else "new"): row(r)[1] for r in returning},
    }


@app.get("/api/session/{sid}")
def session_detail(sid: str):
    ph = "%s" if USE_PG else "?"
    rows = _query(
        f"SELECT event_type, extra_date, time_label, lang, recorded_at "
        f"FROM booking_visitor_events WHERE session_id={ph} ORDER BY recorded_at ASC",
        (sid[:64],)
    )
    def row(r): return list(r.values()) if isinstance(r, dict) else list(r)
    return {"session_id": sid, "events": [
        {"event": row(r)[0], "extra": row(r)[1], "time": row(r)[2], "lang": row(r)[3], "at": str(row(r)[4])}
        for r in rows
    ]}


# ── Sirve la landing (pixel Meta inyectado si hay META_PIXEL_ID) ─────────────
def _serve_index() -> HTMLResponse:
    raw = _INDEX_PATH.read_text(encoding="utf-8")
    body = apply_meta_pixel_placeholder(raw, _META_PIXEL_ID)
    return HTMLResponse(content=body, media_type="text/html; charset=utf-8")


@app.get("/")
def landing_root():
    return _serve_index()


@app.get("/index.html")
def landing_index():
    return _serve_index()


@app.get("/pr")
@app.get("/pr/")
def landing_pt_br():
    """Misma landing; el cliente fuerza idioma según pathname (/pr, /en, /fr)."""
    return _serve_index()


@app.get("/en")
@app.get("/en/")
def landing_en():
    return _serve_index()


@app.get("/fr")
@app.get("/fr/")
def landing_fr():
    return _serve_index()


app.mount("/", StaticFiles(directory=os.path.dirname(__file__) or ".", html=True), name="static")
