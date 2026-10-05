"""The working copy of the vocabulary list: entries not yet accepted."""
import random
import shutil
import unicodedata
from functools import cache
from pathlib import Path

ROOT = Path(__file__).parent
BASE_LIST = ROOT / "VOCABBASE.TXT"
REMAINING = ROOT / "data" / "remaining.txt"
WORD_COUNT = 3500


def fold(entry):
    """Return entry lowercased with accents removed, for comparison and sorting."""
    plain = entry.casefold().replace("œ", "oe").replace("æ", "ae")
    decomposed = unicodedata.normalize("NFKD", plain)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


@cache
def master_list():
    """Return the master list, read once: it never changes while the app runs."""
    return BASE_LIST.read_text(encoding="utf-8").splitlines()


@cache
def master_positions():
    """Return each master-list entry's line index."""
    return {entry: i for i, entry in enumerate(master_list())}


def load_remaining():
    """Return the entries not yet accepted, creating the working copy on first run."""
    if not REMAINING.exists():
        REMAINING.parent.mkdir(exist_ok=True)
        shutil.copyfile(BASE_LIST, REMAINING)
    return [line for line in REMAINING.read_text(encoding="utf-8").splitlines() if line]


def save_remaining(entries):
    """Persist the working list."""
    REMAINING.write_text("\n".join(entries) + "\n", encoding="utf-8")


def pick(count, exclude):
    """Return up to count random entries from the working list, skipping those whose fold is in exclude."""
    pool = [entry for entry in load_remaining() if fold(entry) not in exclude]
    return random.sample(pool, min(count, len(pool)))


def remove(entry):
    """Take an accepted entry out of the working list, matching case and accents loosely."""
    save_remaining([e for e in load_remaining() if fold(e) != fold(entry)])


def is_phrase(entry):
    """Return True if the entry belongs in the phrases section rather than words."""
    position = master_positions().get(entry)
    if position is not None:
        return position >= WORD_COUNT
    return " " in entry.strip()


def restore(entry):
    """Put the master-list spelling of an entry back into the working list, if it has one."""
    remaining = load_remaining()
    missing = [e for e in master_list() if fold(e) == fold(entry) and e not in remaining]
    if missing:
        save_remaining(remaining + missing)
