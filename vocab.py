"""The working copy of the vocabulary list: entries not yet accepted."""
import random
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
BASE_LIST = ROOT / "VOCABBASE.TXT"
REMAINING = ROOT / "data" / "remaining.txt"
WORD_COUNT = 3500


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
    """Take an accepted entry out of the working list."""
    save_remaining([e for e in load_remaining() if e != entry])


def is_phrase(entry):
    """Return True if the entry belongs in the phrases section rather than words."""
    base = BASE_LIST.read_text(encoding="utf-8").splitlines()
    if entry in base:
        return base.index(entry) >= WORD_COUNT
    return " " in entry.strip()


def restore(entry):
    """Put an entry back into the working list if it belongs to the master list."""
    remaining = load_remaining()
    base = BASE_LIST.read_text(encoding="utf-8").splitlines()
    if entry in base and entry not in remaining:
        save_remaining(remaining + [entry])
