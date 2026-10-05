"""Rules for daily pages: what is shown, added, deleted and accepted, and when."""
import threading
from datetime import date

import db
import guardian
import llm
import pdf
import vocab

DAILY_COUNT = 5
MAX_EXAMPLES = 5
# Serialises additions to a day's page, so overlapping requests cannot both make the daily pick.
PAGE_LOCK = threading.Lock()
# Serialises accept and delete, which read the collection, rebuild the PDF and then write.
COLLECTION_LOCK = threading.Lock()
# One lock per entry, so concurrent opens of the same entry generate its detail only once.
DETAIL_LOCKS = {}


class Refused(Exception):
    """An action the rules do not allow; the message is shown to the user."""


def today():
    """Return today's date as YYYY-MM-DD."""
    return date.today().isoformat()


def shown_on(day):
    """Return the folded entries already on a day's page."""
    return {vocab.fold(e["entry"]) for e in db.day_entries(day)}


def pick_into(day, count):
    """Add up to count entries from the working list that are not yet on the day's page; return how many."""
    picked = vocab.pick(count, shown_on(day))
    if picked:
        db.insert_cards(day, llm.card_summaries(picked))
    return len(picked)


def add_random(count):
    """Add up to count random entries to today's page, refusing when none are left."""
    with PAGE_LOCK:
        if not pick_into(today(), count):
            raise Refused("Every entry in the vocabulary list is already on today's page or accepted.")


def todays_entries():
    """Return today's entries, making the daily pick on the first visit of the day."""
    day = today()
    with PAGE_LOCK:
        if not db.day_started(day):
            pick_into(day, DAILY_COUNT)
            db.start_day(day)
    return db.day_entries(day)


def day_entries(day):
    """Return a day's entries: all of them for today, only accepted ones for past days."""
    if day == today():
        return todays_entries()
    return db.day_entries(day, accepted_only=True)


def refuse_if_accepted(text):
    """Refuse if an accepted entry matches text, ignoring case and accents."""
    if vocab.fold(text) in {vocab.fold(e["entry"]) for e in db.accepted_entries()}:
        raise Refused(f'"{text}" is already in your collection.')


def add_typed(text):
    """Add an entry the user typed to today's page."""
    text = text.strip()
    if not text:
        raise Refused("Type a word or phrase to look up.")
    day = today()
    with PAGE_LOCK:
        if vocab.fold(text) in shown_on(day):
            raise Refused(f'"{text}" is already on today\'s page.')
        refuse_if_accepted(text)
        db.insert_cards(day, llm.card_summaries([text]))


def guardian_quotes(entry):
    """Return up to 3 real Guardian sentences that use the entry well."""
    articles = guardian.search(guardian.search_query(entry["entry"]))
    return llm.choose_quotes(entry["entry"], entry["meaning"],
                             guardian.candidates(entry["entry"], articles))


def build_detail(entry):
    """Generate senses and synonyms, with Guardian quotes first and written examples after."""
    detail = llm.entry_detail(entry["entry"])
    quotes = guardian_quotes(entry)
    written = [{"text": text, "source": None} for text in detail["examples"]]
    detail["examples"] = quotes + written[:MAX_EXAMPLES - len(quotes)]
    return detail


def existing(entry_id):
    """Return the entry, refusing if it has been deleted (e.g. from another tab)."""
    entry = db.get(entry_id)
    if entry is None:
        raise Refused("That entry no longer exists. Reload the page.")
    return entry


def detail(entry_id):
    """Return an entry's detail, generating it on first request; concurrent requests wait for it."""
    with DETAIL_LOCKS.setdefault(entry_id, threading.Lock()):
        entry = existing(entry_id)
        if entry["detail"] is None:
            db.set_detail(entry_id, build_detail(entry))
    return existing(entry_id)  # the stored row, exactly as later requests will see it


def editable(entry):
    """Refuse unless the entry is today's, not yet accepted, and its detail is loaded."""
    if entry["accepted"]:
        raise Refused(f'"{entry["entry"]}" is already accepted.')
    if entry["day"] != today():
        raise Refused("Past days are read-only.")
    if entry["detail"] is None:
        raise Refused("Open the entry first so its content is generated.")


def revise(entry_id, feedback):
    """Revise an entry's content according to the learner's feedback."""
    entry = existing(entry_id)
    editable(entry)
    if not feedback.strip():
        raise Refused("Write what should change first.")
    card, new_detail = llm.revise(entry, feedback, MAX_EXAMPLES)
    db.update_card(entry_id, card)
    db.set_detail(entry_id, new_detail)
    return db.get(entry_id)


def publish_pdf(entries):
    """Rebuild the PDF from these accepted entries, refusing if a PDF viewer has it locked."""
    try:
        pdf.build(entries)
    except PermissionError:
        raise Refused("vocabulary.pdf is open in another program. Close it and try again.") from None


def accept(entry_id):
    """Accept an entry: it is final, and leaves the working vocabulary list.

    The PDF is updated first, so a failure leaves nothing changed.
    """
    with COLLECTION_LOCK:
        entry = existing(entry_id)
        editable(entry)
        refuse_if_accepted(entry["entry"])
        publish_pdf(db.accepted_entries() + [{**entry, "accepted": True}])
        db.set_accepted(entry_id)
        vocab.remove(entry["entry"])
    return db.get(entry_id)


def delete(entry_id):
    """Delete today's entry or any accepted entry; accepted ones return to the working list.

    For an accepted entry the PDF is updated first, so a failure leaves nothing changed.
    """
    with COLLECTION_LOCK:
        entry = existing(entry_id)
        if entry["day"] != today() and not entry["accepted"]:
            raise Refused("Past days are read-only.")
        if entry["accepted"]:
            publish_pdf([e for e in db.accepted_entries() if e["id"] != entry_id])
        db.delete(entry_id)
        if entry["accepted"]:
            vocab.restore(entry["entry"])
