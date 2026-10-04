"""SQLite storage for the entries shown each day, their details and acceptance."""
import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "vocab.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS days (day TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY,
    entry TEXT NOT NULL,
    day TEXT NOT NULL,
    card TEXT NOT NULL,
    detail TEXT,
    accepted INTEGER NOT NULL DEFAULT 0
);
"""


def connect():
    """Open the database, creating tables on first use."""
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def to_dict(row):
    """Flatten a row into a dict, merging card fields and decoding the detail."""
    detail = json.loads(row["detail"]) if row["detail"] else None
    return {"id": row["id"], "entry": row["entry"], "day": row["day"],
            "accepted": bool(row["accepted"]), "detail": detail, **json.loads(row["card"])}


def day_started(day):
    """Return True if the daily pick has already been made for this day."""
    with connect() as conn:
        return conn.execute("SELECT 1 FROM days WHERE day = ?", (day,)).fetchone() is not None


def start_day(day):
    """Record that the daily pick has been made for this day."""
    with connect() as conn:
        conn.execute("INSERT OR IGNORE INTO days (day) VALUES (?)", (day,))


def insert_cards(day, cards):
    """Store new cards for a day."""
    with connect() as conn:
        conn.executemany(
            "INSERT INTO entries (entry, day, card) VALUES (?, ?, ?)",
            [(c["entry"], day, json.dumps({k: v for k, v in c.items() if k != "entry"},
                                          ensure_ascii=False)) for c in cards])


def day_entries(day, accepted_only=False):
    """Return a day's entries in the order they were added."""
    sql = "SELECT * FROM entries WHERE day = ?" + (" AND accepted = 1" if accepted_only else "")
    with connect() as conn:
        return [to_dict(r) for r in conn.execute(sql + " ORDER BY id", (day,))]


def accepted_entries():
    """Return all accepted entries alphabetically."""
    with connect() as conn:
        rows = conn.execute("SELECT * FROM entries WHERE accepted = 1 ORDER BY entry COLLATE NOCASE")
        return [to_dict(r) for r in rows]


def find_accepted(entry):
    """Return the accepted entry with this text (case-insensitive), or None."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM entries WHERE accepted = 1 AND LOWER(entry) = LOWER(?)",
                           (entry,)).fetchone()
        return to_dict(row) if row else None


def get(entry_id):
    """Return one entry by id, or None."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        return to_dict(row) if row else None


def set_detail(entry_id, detail):
    """Store the generated detail for an entry."""
    with connect() as conn:
        conn.execute("UPDATE entries SET detail = ? WHERE id = ?",
                     (json.dumps(detail, ensure_ascii=False), entry_id))


def update_card(entry_id, card):
    """Replace an entry's card fields (pronunciation, respelling, meaning)."""
    fields = {k: v for k, v in card.items() if k != "entry"}
    with connect() as conn:
        conn.execute("UPDATE entries SET card = ? WHERE id = ?",
                     (json.dumps(fields, ensure_ascii=False), entry_id))


def set_accepted(entry_id):
    """Mark an entry as accepted."""
    with connect() as conn:
        conn.execute("UPDATE entries SET accepted = 1 WHERE id = ?", (entry_id,))


def delete(entry_id):
    """Remove an entry and everything stored about it."""
    with connect() as conn:
        conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))


def visible_days(today):
    """Return days to show in the calendar: today plus past days with accepted entries."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT day FROM entries WHERE accepted = 1 OR day = ? ORDER BY day DESC",
            (today,))
        return [r["day"] for r in rows]
