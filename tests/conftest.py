"""Shared fixtures: temporary data files, a fixed today, and no LLM or Guardian calls."""
import ctypes
import sys
from contextlib import contextmanager

import pytest
from tenacity import wait_none

import db
import guardian
import journal
import llm
import pdf
import vocab

TODAY = "2030-01-07"
YESTERDAY = "2030-01-06"


def fake_cards(entries):
    """Return a card for each entry without calling the LLM."""
    return [{"entry": e, "pronunciation": "/x/", "respelling": "X", "meaning": f"meaning of {e}"}
            for e in entries]


def fake_detail(entry):
    """Return a detail with one Guardian quote and one written example."""
    quote = {"text": f"A quote with {entry['entry']}.", "source": "The Guardian", "title": "T",
             "url": "https://www.theguardian.com/x", "date": "2025-01-02"}
    return {"senses": [{"part_of_speech": "verb", "definition": "d"}],
            "examples": [quote, {"text": "Written.", "source": None}],
            "synonyms": ["s"], "antonyms": []}


@pytest.fixture(autouse=True)
def app_state(tmp_path, monkeypatch):
    """Point every data file at tmp_path, fix today, and stub the LLM."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "vocab.db")
    monkeypatch.setattr(vocab, "REMAINING", tmp_path / "remaining.txt")
    monkeypatch.setattr(pdf, "PDF_PATH", tmp_path / "vocabulary.pdf")
    monkeypatch.setattr(pdf, "TEMP_PATH", tmp_path / "vocabulary.tmp")
    monkeypatch.setattr(journal, "today", lambda: TODAY)
    monkeypatch.setattr(llm, "card_summaries", fake_cards)
    monkeypatch.setattr(journal, "build_detail", fake_detail)
    for fn in (llm.choose_quotes, llm.entry_detail, llm.revise, guardian.search):
        monkeypatch.setattr(fn.retry, "wait", wait_none())
    return tmp_path


def add_on(day, text):
    """Insert one entry on a day, generate its detail, and return its id."""
    db.insert_cards(day, fake_cards([text]))
    entry_id = db.day_entries(day)[-1]["id"]
    journal.detail(entry_id)
    return entry_id


@contextmanager
def viewer_lock(path):
    """Hold a file open with read-only sharing, as Acrobat Reader does on Windows."""
    if sys.platform != "win32":
        pytest.skip("file locking by viewers is Windows behaviour")
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = ctypes.c_void_p
    handle = k32.CreateFileW(str(path), 0x80000000, 1, None, 3, 0, None)
    assert handle != ctypes.c_void_p(-1).value, ctypes.get_last_error()
    try:
        yield
    finally:
        k32.CloseHandle(ctypes.c_void_p(handle))
