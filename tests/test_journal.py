"""The daily-page rules in journal.py."""
import pytest

import db
import journal
import pdf
import vocab
from conftest import TODAY, YESTERDAY, add_on, viewer_lock


def accepted_texts():
    return [e["entry"] for e in db.accepted_entries()]


def test_daily_pick_happens_once_per_day():
    first = journal.todays_entries()
    assert len(first) == journal.DAILY_COUNT
    assert journal.todays_entries() == first


def test_more_adds_entries_not_already_shown():
    journal.todays_entries()
    journal.add_random(journal.DAILY_COUNT)
    entries = [e["entry"] for e in journal.todays_entries()]
    assert len(entries) == 2 * journal.DAILY_COUNT
    assert len(set(entries)) == len(entries)


def test_typed_duplicate_on_today_is_refused_ignoring_case_and_accents():
    journal.add_typed("façade")
    with pytest.raises(journal.Refused, match="today's page"):
        journal.add_typed("  FACADE ")


def test_accept_removes_from_list_and_builds_pdf():
    entry_id = add_on(TODAY, "abase")
    assert journal.accept(entry_id)["accepted"]
    assert "abase" not in vocab.load_remaining()
    assert pdf.PDF_PATH.exists() and not pdf.TEMP_PATH.exists()


def test_accepted_variant_of_master_entry_removes_master_spelling():
    entry_id = add_on(TODAY, "Abase")
    journal.accept(entry_id)
    assert "abase" not in vocab.load_remaining()


def test_same_entry_cannot_be_accepted_twice_across_days(monkeypatch):
    monkeypatch.setattr(journal, "today", lambda: YESTERDAY)
    journal.accept(add_on(YESTERDAY, "Œuvre"))
    monkeypatch.setattr(journal, "today", lambda: TODAY)
    with pytest.raises(journal.Refused, match="already in your collection"):
        journal.add_typed("œuvre")
    later_id = add_on(TODAY, "oeuvre")
    with pytest.raises(journal.Refused, match="already in your collection"):
        journal.accept(later_id)
    assert accepted_texts() == ["Œuvre"]


def test_accept_requires_detail():
    db.insert_cards(TODAY, [{"entry": "abate", "pronunciation": "", "respelling": "", "meaning": "m"}])
    with pytest.raises(journal.Refused, match="Open the entry first"):
        journal.accept(db.day_entries(TODAY)[-1]["id"])


def test_past_unaccepted_entries_are_read_only():
    entry_id = add_on(YESTERDAY, "abet")
    for action in (lambda: journal.accept(entry_id), lambda: journal.revise(entry_id, "x"),
                   lambda: journal.delete(entry_id)):
        with pytest.raises(journal.Refused, match="Past days are read-only"):
            action()


def test_past_day_shows_only_accepted_entries():
    kept = add_on(YESTERDAY, "abet")
    add_on(YESTERDAY, "abhor")
    db.set_accepted(kept)
    assert [e["entry"] for e in journal.day_entries(YESTERDAY)] == ["abet"]


def test_revise_needs_feedback():
    with pytest.raises(journal.Refused, match="Write what should change"):
        journal.revise(add_on(TODAY, "abet"), "   ")


def test_delete_accepted_restores_list_and_removes_pdf():
    entry_id = add_on(TODAY, "abjure")
    journal.accept(entry_id)
    assert pdf.PDF_PATH.exists()
    journal.delete(entry_id)
    assert "abjure" in vocab.load_remaining()
    assert db.get(entry_id) is None
    assert not pdf.PDF_PATH.exists()


def test_accepted_entry_from_past_day_can_be_deleted():
    entry_id = add_on(YESTERDAY, "abjure")
    db.set_accepted(entry_id)
    journal.delete(entry_id)
    assert db.get(entry_id) is None


@pytest.mark.parametrize("action", ["detail", "revise", "accept", "delete"])
def test_unknown_entry_is_refused(action):
    args = (9999, "x") if action == "revise" else (9999,)
    with pytest.raises(journal.Refused, match="no longer exists"):
        getattr(journal, action)(*args)


def test_accept_with_locked_pdf_changes_nothing():
    journal.accept(add_on(TODAY, "abase"))
    entry_id = add_on(TODAY, "abash")
    before = pdf.PDF_PATH.read_bytes()
    with viewer_lock(pdf.PDF_PATH):
        with pytest.raises(journal.Refused, match="open in another program"):
            journal.accept(entry_id)
    assert accepted_texts() == ["abase"]
    assert "abash" in vocab.load_remaining()
    assert pdf.PDF_PATH.read_bytes() == before
    journal.accept(entry_id)
    assert accepted_texts() == ["abase", "abash"]


def test_delete_with_locked_pdf_changes_nothing():
    entry_id = add_on(TODAY, "abase")
    journal.accept(entry_id)
    with viewer_lock(pdf.PDF_PATH):
        with pytest.raises(journal.Refused, match="open in another program"):
            journal.delete(entry_id)
    assert accepted_texts() == ["abase"]
    assert "abase" not in vocab.load_remaining()
