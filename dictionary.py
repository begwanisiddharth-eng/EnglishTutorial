"""Wiktionary's British pronunciations and senses for master-list entries, built by build_dictionary.py."""
import json
from functools import cache

import vocab

PATH = vocab.ROOT / "dictionary.json"


@cache
def entries():
    """Return the dictionary, read once: it changes only when rebuilt."""
    return json.loads(PATH.read_text(encoding="utf-8"))


def lookup(entry):
    """Return the entry's sense groups, [{ipa, senses}], each with its British IPA or "" if none.

    Empty when Wiktionary does not have the entry, or it is not in the master list.
    """
    return entries().get(vocab.fold(entry), [])
