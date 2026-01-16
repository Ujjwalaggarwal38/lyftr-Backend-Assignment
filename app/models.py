import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .config import DATABASE_URL


def _db_path_from_url(database_url: str) -> str:
    # Supported:
    # sqlite:////data/app.db   (docker)
    # sqlite:////./app.db      (local)
    if not database_url.startswith("sqlite:////"):
        raise ValueError("DATABASE_URL must start with sqlite:////")

    path_part = database_url.replace("sqlite:////", "", 1)

    # Local relative path case like "./app.db"
    if path_part.startswith("./") or path_part.startswith(".\\"):
        return str(Path.cwd() / path_part.replace("\\", "/").replace("./", ""))

    # Absolute linux-style path like "data/app.db" or "/data/app.db"
    if not path_part.startswith("/"):
        path_part = "/" + path_part

    return path_part


def get_conn():
    db_path = _db_path_from_url(DATABASE_URL)

    # ✅ ensure folder exists
    parent = Path(db_path).parent
    parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        message_id TEXT PRIMARY KEY,
        from_msisdn TEXT NOT NULL,
        to_msisdn TEXT NOT NULL,
        ts TEXT NOT NULL,
        text TEXT,
        created_at TEXT NOT NULL
    );
    """)

    conn.commit()
    conn.close()


def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
