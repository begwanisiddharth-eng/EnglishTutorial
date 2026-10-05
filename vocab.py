"""The working copy of the vocabulary list: entries not yet accepted."""
import random
import shutil
import unicodedata
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


def load_remaining():
    """Return the entries not yet accepted, creating the working copy on first run."""
    if not REMAINING.exists():
        REMAINING.parent.mkdir(exist_ok=True)
        shutil.copyfile(BASE_LIST, REMAINING)
    return REMAINING.read_text(encoding="utf-8").splitlines()


def save_remaining(entries):
    """Persist the working list."""
    REMAINING.write_text("\n".join(entries) + "\n", encoding="utf-8")


def pick(count, exclude):
    """Return up to count random entries from the working list, skipping excluded ones."""
    pool = [entry for entry in load_remaining() if entry not in exclude]
    return random.sample(pool, min(count, len(pool)))


def remove(entry):
    """Take an accepted entry out of the working list, matching case and accents loosely."""
    save_remaining([e for e in load_remaining() if fold(e) != fold(entry)])


def is_phrase(entry):
    """Return True if the entry belongs in the phrases section rather than words."""
    base = BASE_LIST.read_text(encoding="utf-8").splitlines()
    if entry in base:
        return base.index(entry) >= WORD_COUNT
    return " " in entry.strip()


def restore(entry):
    """Put the master-list spelling of an entry back into the working list, if it has one."""
    remaining = load_remaining()
    base = BASE_LIST.read_text(encoding="utf-8").splitlines()
    missing = [e for e in base if fold(e) == fold(entry) and e not in remaining]
    if missing:
        save_remaining(remaining + missing)
