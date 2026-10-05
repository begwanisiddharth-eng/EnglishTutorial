"""The daily-page rules in journal.py."""
import threading
import time

import pytest

import db
import journal
import llm
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


def test_entry_with_apostrophe_can_be_accepted():
    entry_id = add_on(TODAY, "a baker's dozen")
    assert journal.accept(entry_id)["accepted"]
    assert "a baker's dozen" not in vocab.load_remaining()


def test_blank_typed_entry_is_refused():
    with pytest.raises(journal.Refused, match="Type a word or phrase"):
        journal.add_typed("   ")
    assert db.day_entries(TODAY) == []


def test_concurrent_first_loads_make_one_daily_pick(monkeypatch):
    slow = llm.completion

    def slow_completion(**kwargs):
        time.sleep(0.2)
        return slow(**kwargs)

    monkeypatch.setattr(llm, "completion", slow_completion)
    threads = [threading.Thread(target=journal.todays_entries) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(db.day_entries(TODAY)) == journal.DAILY_COUNT


def test_random_pick_skips_case_variant_already_on_page():
    vocab.save_remaining(["abase", "abash"])
    journal.add_typed("Abase")
    journal.add_random(2)
    assert [e["entry"] for e in db.day_entries(TODAY)] == ["Abase", "abash"]


def test_detail_puts_guardian_quotes_before_written_examples():
    detail = db.get(add_on(TODAY, "abate"))["detail"]
    sources = [e["source"] for e in detail["examples"]]
    assert sources == ["The Guardian", None, None]
    assert "abate" in detail["examples"][0]["text"]


def test_revise_keeps_quotes_and_applies_the_rest():
    entry_id = add_on(TODAY, "abate")
    quote = db.get(entry_id)["detail"]["examples"][0]
    revised = journal.revise(entry_id, "make the meaning shorter")
    assert revised["meaning"] == "revised meaning"
    assert revised["detail"]["examples"] == [quote, {"text": "A revised example.", "source": None}]


def test_deleted_typed_entry_can_be_looked_up_again():
    journal.add_typed("zugzwang")
    entry_id = db.day_entries(TODAY)[-1]["id"]
    journal.detail(entry_id)
    journal.accept(entry_id)
    journal.delete(entry_id)
    assert "zugzwang" not in vocab.load_remaining()
    journal.add_typed("zugzwang")
    assert db.day_entries(TODAY)[-1]["entry"] == "zugzwang"


def run_together(*actions):
    """Run the actions in parallel threads; return the exceptions they raised."""
    errors = []

    def run(action):
        try:
            action()
        except Exception as error:
            errors.append(error)

    threads = [threading.Thread(target=run, args=(action,)) for action in actions]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return errors


def test_concurrent_accepts_both_reach_the_pdf(monkeypatch):
    first, second = add_on(TODAY, "abase"), add_on(TODAY, "abash")
    build = pdf.JournalDoc.multiBuild
    monkeypatch.setattr(pdf.JournalDoc, "multiBuild", lambda self, story: (time.sleep(0.3), build(self, story)))
    assert run_together(lambda: journal.accept(first), lambda: journal.accept(second)) == []
    data = pdf.PDF_PATH.read_bytes()
    assert accepted_texts() == ["abase", "abash"]
    assert b"(abase)" in data and b"(abash)" in data


def test_concurrent_opens_generate_detail_once(monkeypatch):
    db.insert_cards(TODAY, [{"entry": "abate", "pronunciation": "", "respelling": "", "meaning": "m"}])
    entry_id = db.day_entries(TODAY)[0]["id"]
    detail_calls = []
    fake = llm.completion

    def counting(**kwargs):
        if kwargs["response_format"] is llm.Detail:
            detail_calls.append(1)
            time.sleep(0.2)
        return fake(**kwargs)

    monkeypatch.setattr(llm, "completion", counting)
    assert run_together(*[lambda: journal.detail(entry_id)] * 3) == []
    assert len(detail_calls) == 1


def act_during_revision(monkeypatch, action):
    """Make the revision's LLM call run action first, as a click arriving mid-revision would."""
    fake = llm.completion

    def completion(**kwargs):
        if kwargs["response_format"] is llm.Revision:
            action()
        return fake(**kwargs)

    monkeypatch.setattr(llm, "completion", completion)


def test_revision_finishing_after_accept_is_refused_and_pdf_matches(monkeypatch):
    entry_id = add_on(TODAY, "abate")
    act_during_revision(monkeypatch, lambda: journal.accept(entry_id))
    with pytest.raises(journal.Refused, match="already accepted"):
        journal.revise(entry_id, "make the meaning shorter")
    assert db.get(entry_id)["meaning"] == "meaning of abate"


def test_revision_finishing_after_delete_is_refused(monkeypatch):
    entry_id = add_on(TODAY, "abate")
    act_during_revision(monkeypatch, lambda: journal.delete(entry_id))
    with pytest.raises(journal.Refused, match="no longer exists"):
        journal.revise(entry_id, "make the meaning shorter")


def test_more_with_nothing_left_is_refused_without_an_llm_call(monkeypatch):
    vocab.save_remaining([])
    monkeypatch.setattr(llm, "completion", lambda **kwargs: pytest.fail("LLM called with nothing to pick"))
    with pytest.raises(journal.Refused, match="Every entry"):
        journal.add_random(journal.DAILY_COUNT)
    assert journal.todays_entries() == []
