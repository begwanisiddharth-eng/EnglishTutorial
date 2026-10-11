# Review: Wiktionary pronunciations

## Sixth round: Wiktionary for pronunciations only

Word Bank at `b1c8b70` plus the uncommitted change below, 11 October 2026.
133 unit tests pass; the end-to-end run passed 41 of 41.

### Why

The fifth round grounded meanings in Wiktionary's senses. Its own side-by-side
check (30 entries: 1 better, 3 worse or debatable) and later examples ("cognate"
opening with "related by blood") showed the grounding did not pay: Wiktionary
lists senses roughly in historical order, and the model leads with whatever
comes first. So meanings are the model's own again, and Wiktionary supplies
only British IPA.

### What changed

| Part | Change |
|---|---|
| `llm.py` | The detail prompt is back to its pre-Wiktionary wording. The card prompt gives a single IPA directly; only entries with several pronunciations list their senses, explicitly only for choosing the IPA. `fits` checks the group only where several are listed |
| `build_dictionary.py` | `needed()` keeps an entry only if it has a British IPA, and senses only when there are several pronunciations. `dictionary.json` went from about 1.5 MB to 207 KB; still 2,384 entries, 91 with several pronunciations |
| `pdf.py` | The credit names pronunciations only |
| Tests | 133 (from 127): single-IPA entries, the group ignored where only one is listed, `needed()`, the detail prompt carrying no senses, and quotes not stored as written examples (D6) |

### Measurements

**Meanings**, 30 fresh entries, all three versions run on gpt-4o-mini:

| Version | Against the pre-Wiktionary meanings |
|---|---|
| Grounded in senses (`b1c8b70`) | 5 worse, 0 better: "caliber" (bore of a gun), "diaspora" (Jews only), "quash", "purport", "ashen" (muddled senses) |
| Now | About the same on 28; 2 debatable ("amplify" narrowed to sound, "bereft" oddly worded) |

Both Wiktionary versions used American spellings twice ("specialized", "gray");
the pre-Wiktionary run did not. The prompts ask for British spelling in all
three, so this looks like sampling variation, but it is noted.

**Card prompt size** (median of 40 batches of 5, prompt text only): 261 tokens
before Wiktionary, 734 with senses, **428 now**.

**A normal day** (5 cards, 5 entries opened, 3 edits) is 14 calls and 13,232
tokens on gpt-4o-mini. Groq's per-minute limiter counted each request at 1,600
to 2,800 tokens (from its refusal messages), so opening a new entry costs 4,000
to 5,000 of its 8,000 a minute: two first opens within a minute usually send the
second to OpenAI. The daily 200,000 holds such a day several times over.

### End-to-end testing

The same script as the fifth round, with one check added (below), against a
fresh copy of the data, Groq first.

| Result | Detail |
|---|---|
| **41 of 41** | Daily pick, typed entries, 5 More, refusals, detail (concurrent opens pay once), revisions (quotes and pronunciation kept unless asked), accept and delete with PDF checks, PDF locked, accept racing an edit, past days |
| Wiktionary IPA | Used on 9 of the 9 cards that had one; "buffet" got the meal pronunciation, "adept" one of its two |
| Fallbacks | 12, all Groq's per-minute limit (5 detail, 5 quote choice, 2 revision). Every card batch was answered by Groq, and none was rejected |
| Errors | 0 tracebacks, 0 5xx |

A first attempt stopped at check 4 because the copy still had today's page from
a measurement script; the copy was refreshed from `data/` and rerun. The
project's `data/` and `output/` were not changed.

### Defect found and fixed

| # | Severity | Finding | Evidence | Fix |
|---|---|---|---|---|
| D6 | Medium | **Edit could copy a Guardian quote into the written examples**, so it appeared twice, the copy labelled "Example sentence" | Seen on "cognate". Measured: 2 of 12 unrelated edits, both answered by gpt-4o-mini (2 of its 7; Groq 0 of 5). Root cause: the model returns the quote text in `written_examples`, and `llm.revise` stored them all | `llm.revise` drops written examples that match any of the entry's quotes, kept or dropped, by `letters()`. Two regression tests failed before the fix. Live retest on gpt-4o-mini: the model returned a copy in 1 of 12 revisions; 0 of 12 stored one |

### Remaining (not code defects)

- 52% of entries have no British IPA in Wiktionary (phrases especially: 242 of
  1,500) and get the model's.
- Respellings are written by the model; Groq formats about 1 in 9 wrongly
  ("BUH-fay" for /ˈbʊfeɪ/).
- Wiktionary's notation shows through in places: `/(ˌ)ʌnˈfæðəməbl̩/`.
- Examples usually show one or two meanings: the three quote places are chosen
  for the principal meaning only.

## Fifth round: Wiktionary added (summary)

Commit `b1c8b70`. British IPA and senses from Wiktionary via kaikki.org, grouped
by pronunciation so homographs keep each IPA with its senses; variants follow
their main spellings ("gibe" -> jibe, gybe); comma-split links are not followed.
The model picks a group number and the code copies its IPA. E2E: 40 of 40 with
Groq first and again with Groq unreachable.

Defects found and fixed then, all still in force:

| # | Finding | Fix |
|---|---|---|
| D1 | Edit rewrote the pronunciation on unrelated feedback | `feedback_asks_to_change_pronunciation` gates it |
| D2 | gpt-4o-mini returned one card per group, misplacing meanings (8 of 8 runs) | Cards echo `entry`; `llm.fits` rejects mismatches |
| D3 | Groq misspelt a long field name | Field renamed to `group` |
| D4 | "gibe" lost its taunting sense | Equal shares across main spellings |
| D5 | "close but no cigar" took the senses of "close" | Multi-target links not followed |

Superseded by the sixth round: meanings and detail senses grounded in
Wiktionary's senses.
