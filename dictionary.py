"""Wiktionary's British pronunciations for master-list entries, built by build_dictionary.py."""
import json
from functools import cache

import vocab

PATH = vocab.ROOT / "dictionary.json"


@cache
def entries():
    """Return the dictionary, read once: it changes only when rebuilt."""
    return json.loads(PATH.read_text(encoding="utf-8"))


def lookup(entry):
    """Return the entry's pronunciation groups, [{ipa, senses}].

    One group: its ipa is the entry's pronunciation, and senses is empty. Several: each group has
    its senses, so the meaning on the card can pick its pronunciation; ipa is "" for senses with no
    British pronunciation. Empty when Wiktionary has no British pronunciation, or the entry is not
    in the master list.
    """
    return entries().get(vocab.fold(entry), [])
