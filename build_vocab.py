"""Validate vocabulary part files and assemble VOCABBASE.TXT.

Usage:
    uv run build_vocab.py          # report only
    uv run build_vocab.py --write  # also write VOCABBASE.TXT if valid
"""
import sys
import unicodedata
from pathlib import Path

PARTS = Path("parts")
OUTPUT = Path("VOCABBASE.TXT")
WORD_TARGET = 3500
PHRASE_TARGET = 1500
SUFFIXES = ("ly", "ness", "ity", "ion", "ation", "ment", "ous", "ance",
            "ence", "al", "ic", "ism", "ist", "ize", "s", "ed", "ing", "y")


def load(pattern):
    """Return non-blank stripped lines from all part files matching pattern."""
    entries = []
    for path in sorted(PARTS.glob(pattern)):
        lines = path.read_text(encoding="utf-8").splitlines()
        entries += [line.strip() for line in lines if line.strip()]
    return entries


def fold(entry):
    """Return entry lowercased with accents removed, for comparison."""
    plain = entry.casefold().replace("œ", "oe").replace("æ", "ae")
    decomposed = unicodedata.normalize("NFKD", plain)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def duplicates(entries):
    """Return entries that repeat (ignoring case and accents)."""
    seen, dups = set(), []
    for entry in entries:
        key = fold(entry)
        if key in seen:
            dups.append(entry)
        seen.add(key)
    return dups


def derived_pairs(words):
    """Return (base, derived) pairs where one word is a suffixed form of another."""
    keys = {w.casefold() for w in words}
    pairs = []
    for word in sorted(keys):
        for suffix in SUFFIXES:
            if not word.endswith(suffix):
                continue
            stem = word[: -len(suffix)]
            for base in (stem, stem + "e"):
                if base in keys and base != word:
                    pairs.append((base, word))
    return pairs


def report(words, phrases):
    """Print validation results; return True if the set is complete and clean."""
    dups = duplicates(words + phrases)
    spaced = [w for w in words if " " in w]
    derived = derived_pairs(words)
    print(f"words: {len(words)}/{WORD_TARGET}  phrases: {len(phrases)}/{PHRASE_TARGET}")
    print(f"duplicates: {dups}")
    print(f"words containing spaces: {spaced}")
    print(f"possible derived pairs: {derived}")
    return (len(words) == WORD_TARGET and len(phrases) == PHRASE_TARGET
            and not dups and not spaced)


def write(words, phrases):
    """Write words then phrases, each sorted ignoring case and accents."""
    lines = sorted(words, key=fold) + sorted(phrases, key=fold)
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {len(lines)} lines to {OUTPUT}")


def main():
    words, phrases = load("words_*.txt"), load("phrases_*.txt")
    valid = report(words, phrases)
    if "--write" in sys.argv:
        if valid:
            write(words, phrases)
        else:
            print("not written: validation failed")


if __name__ == "__main__":
    main()
