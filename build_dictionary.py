"""Build dictionary.json: British pronunciations and senses from Wiktionary for the master list.

The source is kaikki.org's extract of English Wiktionary (CC BY-SA). It is downloaded to
downloads/ on first use (about 520 MB); each pass over it takes about a minute.

Usage:
    uv run build_dictionary.py
"""
import gzip
import json
import shutil
import urllib.request
from collections import defaultdict

import dictionary
import vocab

URL = "https://kaikki.org/dictionary/English/kaikki.org-dictionary-English.jsonl.gz"
DUMP = vocab.ROOT / "downloads" / "kaikki-English.jsonl.gz"
BRITISH = {"Received-Pronunciation", "UK", "British"}
# A British transcription with one of these tags is not the standard modern one.
UNUSUAL = {"obsolete", "archaic", "dated", "rare", "uncommon", "nonstandard", "dialectal", "proscribed",
           "Scotland", "Wales", "Northern-England", "Northern-Ireland", "Ireland"}
MAX_SENSES = 8
# Wiktionary writes r as ɹ and marks syllables, affricates (tie bar) and diphthongs (non-syllabic
# mark); the Oxford and Cambridge style does not.
NOTATION = str.maketrans({"ɹ": "r", ".": None, "\N{COMBINING DOUBLE INVERTED BREVE}": None,
                          "\N{COMBINING INVERTED BREVE BELOW}": None})


def download():
    """Fetch the kaikki.org English extract unless it is already there."""
    if not DUMP.exists():
        DUMP.parent.mkdir(exist_ok=True)
        print(f"downloading {URL}")
        with urllib.request.urlopen(URL) as response, open(DUMP.with_suffix(".part"), "wb") as out:
            shutil.copyfileobj(response, out)
        DUMP.with_suffix(".part").replace(DUMP)


def records_for(words):
    """Return the dump's records whose folded word is in words, grouped by folded word."""
    found = defaultdict(list)
    with gzip.open(DUMP, "rt", encoding="utf-8") as dump:
        for line in dump:
            record = json.loads(line)
            if vocab.fold(record["word"]) in words:
                found[vocab.fold(record["word"])].append(record)
    return found


def matching(entry, records):
    """Return the records for exactly this spelling if there are any, else all that fold the same.

    So "august" (majestic) does not take the pronunciation of the month "August".
    """
    exact = [r for r in records if r["word"] == entry]
    return exact or records


def british_ipa(record):
    """Return the record's first standard British phonemic transcription, in Oxford notation, or None."""
    for sound in record.get("sounds", []):
        ipa, tags = sound.get("ipa", ""), set(sound.get("tags", []))
        whole = ipa.startswith("/") and ipa.endswith("/") and "-" not in ipa
        if whole and BRITISH & tags and not UNUSUAL & tags:
            return ipa.translate(NOTATION)
    return None


def real_senses(record):
    """Return the record's senses that define something, not cross-references or obsolete ones."""
    return [s for s in record["senses"] if s.get("glosses") and "alt_of" not in s and "form_of" not in s
            and "obsolete" not in s.get("tags", [])]


def sense_lines(record):
    """Return the record's senses as "(part of speech) definition", with Wiktionary's labels."""
    return [f"({record['pos']}) {': '.join(s.get('raw_glosses', s['glosses']))}" for s in real_senses(record)]


def groups(records, limit=MAX_SENSES):
    """Return the senses grouped by British pronunciation, in Wiktionary's order.

    A record covers one part of speech of one origin; records with the same pronunciation share a
    group, and those without a British one share the group with ipa "". So "buffet" (furniture,
    /ˈbʊfeɪ/) and "buffet" (to strike, no British IPA in Wiktionary) stay apart.
    At most limit senses in all.
    """
    by_ipa = defaultdict(list)
    for record in records:
        by_ipa[british_ipa(record) or ""] += sense_lines(record)
    room, result = limit, []
    for ipa, lines in by_ipa.items():
        lines = list(dict.fromkeys(lines))[:room]
        room -= len(lines)
        if ipa or lines:
            result.append({"ipa": ipa, "senses": lines})
    return result


def main_spellings(records):
    """Return the main spellings of an entry with no senses of its own (e.g. valor -> valour).

    A link with several targets is skipped: wiktextract splits a target with a comma, so
    "close, but no cigar" becomes "close" and "but no cigar".
    """
    if not records or any(real_senses(r) for r in records):
        return []
    targets = [s["alt_of"][0]["word"] for r in records for s in r["senses"] if len(s.get("alt_of", [])) == 1]
    return list(dict.fromkeys(targets))


def lookup_entry(records, targets):
    """Return the entry's groups, taken from its main spellings when the entry is only a variant.

    Each main spelling gets an equal share of the senses, so "gibe" keeps the taunting sense of
    "jibe" as well as the sailing sense of "gybe".
    """
    spellings = main_spellings(records)
    if not spellings:
        return groups(records)
    share = MAX_SENSES // len(spellings)
    combined = defaultdict(list)
    for spelling in spellings:
        for group in groups(matching(spelling, targets.get(vocab.fold(spelling), [])), share):
            combined[group["ipa"]] += group["senses"]
    return [{"ipa": ipa, "senses": senses} for ipa, senses in combined.items()] or groups(records)


def build():
    """Write dictionary.json for every master-list entry Wiktionary knows."""
    download()
    entries = {vocab.fold(e): e for e in vocab.master_list() if e}
    found = {key: matching(entries[key], records) for key, records in records_for(entries.keys()).items()}
    variants = {vocab.fold(v) for records in found.values() for v in main_spellings(records)}
    targets = records_for(variants)
    result = {key: g for key in entries if (g := lookup_entry(found.get(key, []), targets))}
    dictionary.PATH.write_text(json.dumps(result, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    with_ipa = sum(any(g["ipa"] for g in v) for v in result.values())
    print(f"{len(result)} of {len(entries)} entries; {with_ipa} with a British pronunciation")


if __name__ == "__main__":
    build()
