# Review: fifth round, Wiktionary pronunciations and senses

Word Bank at `26c9610` plus the uncommitted Wiktionary change, 11 October 2026.
The change takes British IPA and senses from Wiktionary. It was then tested end
to end with real Groq, OpenAI and Guardian calls, against a copy of the data.
**Every defect found has been fixed.** 127 unit tests pass.

## What changed

| Part | Change |
|---|---|
| `build_dictionary.py` (new) | One pass over the kaikki.org English extract (523 MB, about 2 minutes). Writes `dictionary.json`: per entry, sense groups `[{ipa, senses}]`, one per British IPA |
| `dictionary.py` (new) | `lookup(entry)` by `vocab.fold`; the file is read once |
| `llm.py` | The card prompt lists each entry's numbered groups; the model returns the group number and the code copies its IPA. The detail prompt is given Wiktionary's senses. Revise keeps the pronunciation unless asked |
| `pdf.py` | CC BY-SA credit on the title page |
| Tests | 20 new: the builder's rules, group choice, reply matching, the pronunciation gate |

Coverage: 4,426 of 5,000 entries are in Wiktionary (3,496 of 3,500 words, 932
of 1,500 phrases); 2,384 have a British IPA (2,144 words, 242 phrases).

## Design decisions and the evidence for them

| Decision | Why |
|---|---|
| Only IPA tagged Received-Pronunciation, UK or British | Untagged IPA in Wiktionary is often American |
| Group senses by IPA, and let the model pick a group number | Homographs ("buffet", "adept", "abject") have a different pronunciation per sense. The model never retypes IPA, so it cannot corrupt it |
| Follow a variant to every single-target main spelling, with an equal share of senses | "gibe" went only to "gybe" (sailing) and lost the taunting sense. Every multi-target link in the data was a wiktextract comma split ("close but no cigar" -> "close"), so those are not followed. A similarity check was tried first; "but no cigar" passed it, so it was dropped |
| Normalise notation (`ɹ` to `r`, no syllable dots or tie bars) | Matches the IPA style the app already used: `/əˈbɹɪd͡ʒ.aɪ̯/` becomes `/əˈbrɪdʒaɪ/` |

## Defects found and fixed

| # | Severity | Finding | Root cause | Fix |
|---|---|---|---|---|
| D1 | High | **Edit rewrote the pronunciation on unrelated feedback**, replacing Wiktionary's IPA with the model's | The revision returned a pronunciation and the code always used it; models rewrite it freely | `feedback_asks_to_change_pronunciation`, decided first, gates it, as for quote removal. Regression test fails without the gate; live check passed |
| D2 | High | gpt-4o-mini returned one card per Wiktionary group instead of one per entry (6 cards for 5 entries, in 8 of 8 runs), so meanings landed on the wrong entries | Cards were matched to entries by position, and the listing invited a card per group | Each card echoes its `entry`; `llm.fits` rejects a batch whose entries differ (by `letters`: fold, then alphanumerics) or that names a missing group, so the call retries or falls back. 12 of 12 batches then correct; 40 entries with no rejection |
| D3 | Medium | Groq misspelt a long field name ("wikictionary_group"), failing the reply | Model typo on an unusual key | Field renamed to `group` |
| D4 | Medium | "gibe" lost its main sense | See variants above | Equal shares across main spellings |
| D5 | Low | "close but no cigar" took the senses of "close" | wiktextract comma split | Multi-target links not followed |

Two fixes were tried and reverted because measurement showed no gain: a hint to
prefer the commonest sense over the first listed ("terra firma" still led with
the legal sense).

## End-to-end testing

A script of 40 checks ran against a running server on a copy of the code and
data. It covers the whole lifecycle: local-only middleware, the daily pick
(made once), typed entries with and without accents, 5 More, refusals (blank,
duplicate, already accepted, past day), detail generation (concurrent opens pay
once, quotes first, at most 5 examples), revisions (quotes kept unless asked,
pronunciation kept, exact quote removal), accept and delete with PDF checks,
the PDF locked by a viewer, an accept racing an edit, and the Wiktionary
behaviour below.

| Run | Setup | Result |
|---|---|---|
| 1 | Groq first | 38 of 40. Failures: D1, and a bug in the test script itself (it typed an entry still on today's page); both fixed |
| 2 | Groq first | **40 of 40.** 13 fallbacks, all Groq rate limits; no tracebacks or 5xx. Wiktionary IPA used on 12 of the 12 cards that had one |
| 3 | Groq unreachable (all OpenAI) | **40 of 40.** 22 fallbacks; Wiktionary IPA used on 10 of 10 |
| - | `GROQ_API_KEY=bad` | Reported as a rejected key in 0.48 s, no fallback |
| - | Browser (Playwright) | IPA and grounded senses shown; 0 console errors |

Wiktionary checks that passed: "raison d'etat" typed without the accent gets
`/reɪˌzɒ̃ deɪˈtɑː/`; "unfathomable" has the stress on "fath" (Groq had put it on
"thom"); "buffet" as a meal gets `/ˈbʊfeɪ/`; "adept" gets one of its two IPAs;
"gibe" includes the taunting sense; "photobomb" (not in the list) gets the
model's IPA; the PDF contains the IPA and the credit.

## Measurements

| Measure | Before | After |
|---|---|---|
| Card batch prompt (median tokens) | 349 | 748 |
| Malformed respellings, Groq (of 40) | 2 | 4-5 |
| Malformed respellings, gpt-4o-mini (of 40) | - | 0-1 |
| Card meanings, 30 compared side by side | - | 26 as good, 1 better, 3 worse or debatable |

## Remaining (not code defects)

- **52% of entries have no British IPA in Wiktionary**, phrases especially
  (242 of 1,500). They get the model's IPA.
- **Respellings are still written by the model;** Groq's were no better for
  having the IPA ("uh-DEP-t" in run 2). Deriving them from the IPA in code would
  fix this.
- **Wiktionary's own notation shows through** in places: optional stress
  `(ˌ)` and syllabic marks (`/(ˌ)ʌnˈfæðəməbl̩/`). Correct, but less tidy.
- **Meanings sometimes follow Wiktionary's first-listed sense** rather than the
  commonest.
- **Typed entries outside the master list** get no Wiktionary data.
- **Wiktionary gaps:** some common words ("genesis") have no British IPA.
