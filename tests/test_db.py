"""SQLite storage."""
import sqlite3

import pytest

import db
from conftest import TODAY, fake_cards


def test_connection_is_closed_after_use():
    with db.connect() as conn:
        conn.execute("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        conn.execute("SELECT 1")


def test_failed_transaction_is_rolled_back():
    with pytest.raises(RuntimeError):
        with db.connect() as conn:
            conn.execute("INSERT INTO days (day) VALUES (?)", (TODAY,))
            raise RuntimeError
    assert not db.day_started(TODAY)


def test_entries_round_trip_with_card_fields_flattened():
    db.insert_cards(TODAY, fake_cards(["Œuvre"]))
    entry = db.day_entries(TODAY)[0]
    assert (entry["entry"], entry["meaning"], entry["detail"], entry["accepted"]) == \
        ("Œuvre", "meaning of Œuvre", None, False)


def test_deleted_database_is_recreated():
    db.start_day(TODAY)
    db.DB_PATH.unlink()
    assert not db.day_started(TODAY)
