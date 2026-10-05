"""Shared fixtures: temporary data files, a fixed today, and fakes at the two network boundaries.

Only llm.completion and guardian.search are replaced, so every layer above them
(card summaries, detail building, quote choosing, revision) runs for real.
"""
import ctypes
import json
import re
import sys
from contextlib import contextmanager
from types import SimpleNamespace

import litellm
import pytest

import db
import guardian
import journal
import llm
import pdf
import vocab

TODAY = "2030-01-07"
YESTERDAY = "2030-01-06"
ARTICLE_DATE = "2025-01-02"
REAL_SEARCH = guardian.search


def reply(data):
    """Wrap data as a LiteLLM completion response."""
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(data)))])


def fake_answer(prompt, schema):
    """Return a valid reply for each prompt type, without calling an LLM."""
    if schema is llm.CardBatch:
        entries = re.findall(r"^\d+\. (.*)$", prompt.split("Entries:")[1], re.MULTILINE)
        return {"cards": [{"pronunciation": "/x/", "respelling": "X", "meaning": f"meaning of {e}"}
                          for e in entries]}
    if schema is llm.Detail:
        return {"senses": [{"part_of_speech": "verb", "definition": "d"}],
                "examples": ["A written example.", "Another written example."],
                "synonyms": ["s"], "antonyms": []}
    if schema is llm.Choice:
        return {"chosen": [1]}
    return {"pronunciation": "/y/", "respelling": "Y", "meaning": "revised meaning",
            "senses": [{"part_of_speech": "noun", "definition": "r"}], "keep_quotes": [1],
            "written_examples": ["A revised example."], "synonyms": [], "antonyms": []}


def fake_completion(model, messages, response_format, timeout):
    """Stand in for litellm.completion."""
    return reply(fake_answer(messages[0]["content"], response_format))


def fake_search(query):
    """Return one Guardian article that uses every quoted part of the query in a usable sentence."""
    words = " ".join(re.findall(r'"([^"]+)"', query))
    text = f"Short. Critics said the plan would {words} the debate for many years to come."
    return [{"title": "T", "url": "https://www.theguardian.com/x", "date": ARTICLE_DATE, "text": text}]


def fake_cards(entries):
    """Return a card for each entry, for inserting rows directly."""
    return [{"entry": e, "pronunciation": "/x/", "respelling": "X", "meaning": f"meaning of {e}"}
            for e in entries]


@pytest.fixture(autouse=True)
def app_state(tmp_path, monkeypatch):
    """Point every data file at tmp_path, fix today, and fake the network."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "vocab.db")
    monkeypatch.setattr(vocab, "REMAINING", tmp_path / "remaining.txt")
    monkeypatch.setattr(pdf, "PDF_PATH", tmp_path / "vocabulary.pdf")
    monkeypatch.setattr(pdf, "TEMP_PATH", tmp_path / "vocabulary.tmp")
    monkeypatch.setattr(journal, "today", lambda: TODAY)
    monkeypatch.setattr(llm, "completion", fake_completion)
    monkeypatch.setattr(guardian, "search", fake_search)
    for fn in (llm.card_summaries, llm.choose_quotes, llm.entry_detail, llm.revise, REAL_SEARCH):
        monkeypatch.setattr(fn.retry, "sleep", lambda seconds: None)
    return tmp_path


def add_on(day, text):
    """Insert one entry on a day, generate its detail, and return its id."""
    db.insert_cards(day, fake_cards([text]))
    entry_id = db.day_entries(day)[-1]["id"]
    journal.detail(entry_id)
    return entry_id


def groq_invalid_key():
    """Return the error litellm raises for Groq's "Invalid API Key": a BadRequestError with status 401."""
    error = litellm.BadRequestError("Invalid API Key", model="m", llm_provider="groq")
    error.status_code = 401
    return error


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
