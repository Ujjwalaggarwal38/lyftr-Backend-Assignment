import sqlite3
from .models import get_conn, utc_now_iso
from typing import Optional, Dict, Any, List


def insert_message(message_id: str, from_msisdn: str, to_msisdn: str, ts: str, text: str | None):
    """
    Returns:
      created: bool
      duplicate: bool
    """
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO messages (message_id, from_msisdn, to_msisdn, ts, text, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (message_id, from_msisdn, to_msisdn, ts, text, utc_now_iso()))
        conn.commit()
        return True, False

    except sqlite3.IntegrityError:
        # message_id already exists -> duplicate
        return False, True

    finally:
        conn.close()



def _build_filters(from_msisdn: Optional[str], since: Optional[str], q: Optional[str]):
    where_clauses = []
    params = []

    if from_msisdn:
        where_clauses.append("from_msisdn = ?")
        params.append(from_msisdn)

    if since:
        where_clauses.append("ts >= ?")
        params.append(since)

    if q:
        # case-insensitive search in SQLite
        where_clauses.append("LOWER(COALESCE(text, '')) LIKE ?")
        params.append(f"%{q.lower()}%")

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    return where_sql, params


def count_messages(from_msisdn: Optional[str], since: Optional[str], q: Optional[str]) -> int:
    where_sql, params = _build_filters(from_msisdn, since, q)

    conn = get_conn()
    cur = conn.cursor()

    cur.execute(f"""
        SELECT COUNT(*) as cnt
        FROM messages
        {where_sql}
    """, params)

    row = cur.fetchone()
    conn.close()

    return int(row["cnt"]) if row else 0


def fetch_messages(
    from_msisdn: Optional[str],
    since: Optional[str],
    q: Optional[str],
    limit: int,
    offset: int
) -> List[Dict[str, Any]]:
    where_sql, params = _build_filters(from_msisdn, since, q)

    conn = get_conn()
    cur = conn.cursor()

    cur.execute(f"""
        SELECT message_id, from_msisdn, to_msisdn, ts, text, created_at
        FROM messages
        {where_sql}
        ORDER BY ts ASC, message_id ASC
        LIMIT ? OFFSET ?
    """, params + [limit, offset])

    rows = cur.fetchall()
    conn.close()

    data = []
    for r in rows:
        data.append({
            "message_id": r["message_id"],
            "from": r["from_msisdn"],
            "to": r["to_msisdn"],
            "ts": r["ts"],
            "text": r["text"],
            "created_at": r["created_at"],
        })

    return data



def get_stats() -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()

    # total messages
    cur.execute("SELECT COUNT(*) AS cnt FROM messages")
    total_messages = int(cur.fetchone()["cnt"])

    # unique senders
    cur.execute("SELECT COUNT(DISTINCT from_msisdn) AS cnt FROM messages")
    senders_count = int(cur.fetchone()["cnt"])

    # top 10 senders
    cur.execute("""
        SELECT from_msisdn AS sender, COUNT(*) AS cnt
        FROM messages
        GROUP BY from_msisdn
        ORDER BY cnt DESC
        LIMIT 10
    """)
    rows = cur.fetchall()
    messages_per_sender = [{"from": r["sender"], "count": int(r["cnt"])} for r in rows]

    # first + last message ts
    cur.execute("SELECT ts FROM messages ORDER BY ts ASC, message_id ASC LIMIT 1")
    r1 = cur.fetchone()
    first_ts = r1["ts"] if r1 else None

    cur.execute("SELECT ts FROM messages ORDER BY ts DESC, message_id DESC LIMIT 1")
    r2 = cur.fetchone()
    last_ts = r2["ts"] if r2 else None

    conn.close()

    return {
        "total_messages": total_messages,
        "senders_count": senders_count,
        "messages_per_sender": messages_per_sender,
        "first_message_ts": first_ts,
        "last_message_ts": last_ts,
    }

