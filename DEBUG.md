# Debug report

Word Bank, 5 October 2026, fourth round. Covers the end-to-end test that produced
REVIEW.md, the fixes, and the retest. Earlier rounds are in git history.

## How it was tested

- **Reproduce first.** Each defect was reproduced, its root cause shown, and a
  regression test written. Each test was run against the unfixed code and
  failed there. The one exception is L1: its test needs a function the fix
  introduces, so the bug was shown directly with old and new `.env` loading
  instead.
- **Real services.** Groq (`groq/openai/gpt-oss-120b`), OpenAI
  (`openai/gpt-4o-mini`, chosen per run with `LLM_MODEL=… uv run --env-file
  .env`), and The Guardian. Keys were never printed or copied.
- **Real data protected.** Every server ran from a scratch copy. `data/` and
  `output/` are unchanged from `HEAD`.
- **Browser.** Chromium through Playwright. PDF text was read back with
  `pypdf` (`uv run --with`, not a project dependency).

## What was found, and how it was proved

| # | Defect | Proof before the fix | Proof after |
|---|---|---|---|
| H1 | Edit deleted Guardian quotes unasked | Groq: 7 of 24 unrelated revisions lost quotes; gpt-4o-mini 3 of 12; even an ungated `drop_quotes`, 4 of 33 | Gated: 0 of 33 unrelated, 12 of 12 requested drops exact; end to end 0 of 9 |
| H2 | Edit raced Accept and Delete | Accept 0.3 s into an Edit: DB had the revised meaning, PDF the old; Delete gave `200 null`; Accept enabled during Edit in the page | Edit refused with "already accepted" / "no longer exists"; DB and PDF agree; footer locked during Edit and Accept (Chromium) |
| M1 | Closing quote mark cut off | `SENTENCE_END.split('“… crime.” The…')` lost `”`; 2 of 30 stored quotes | 68 stored quotes from two runs checked word for word against their articles: 0 problems |
| M2 | Groq daily limit retried, wrong message | 74.1 s, then "Try again in a minute" | Live: 0.7 s, "Groq's daily token allowance is used up…" |
| L1 | Blank key passed startup | `GROQ_API_KEY=` in `.env` gave `missing_keys: []` | `['GROQ_API_KEY']` |
| L2 | Search not accent-insensitive | "etat" found nothing | "etat" and "ÉTAT" find "raison d'état" |
| L3 | Card title under the badge | Measured: button 258 px wide in a 229 px card; badge over the title | 20 cards: none overlaps its badge or overflows; no sideways scroll |

## Retest

### Automated

`uv run pytest`: **100 passed** (91 before). Nine tests are new:

- `test_llm.py`: quotes kept when the reply omits them; drops ignored unless
  the gate is set; drops applied when it is; the daily limit not retried.
- `test_journal.py`: a revision finishing after Accept, and after Delete.
- `test_guardian.py`: closing quote marks stay with their sentence.
- `test_server.py`: the daily-limit message; a blank key in `.env` is named.

### End to end, gpt-4o-mini and The Guardian

**41 of 41 checks passed** on the fixed code. The server log had 0 tracebacks,
0 × 5xx and 0 retried LLM attempts. Every 4xx was a deliberate refusal.

| Area | Result |
|---|---|
| Daily pick | 5 cards in 4.2 s; no repick; no pronunciation for long phrases |
| Typed entries | Placeholder phrase, accented apostrophe, non-master word; case, accent and blank refusals |
| Detail | 12 concurrent opens (one entry three times) all 200; slowest 5.8 s (Groq: 81 s); the three copies identical; 36 quotes with URL and date |
| Revise | 9 unrelated edits kept every quote; "Drop the second Guardian quote" dropped exactly that one |
| Races | Accept and Delete during an Edit both resolved correctly |
| Accept and PDF | Entries in the PDF; second accept, accept before opening, revise after accept, and past-day changes all refused |
| Locked PDF | Refused with the viewer message; nothing changed; succeeds after release |
| Delete | Master entry back in the list and out of the PDF; typed entry not added, and can be typed again |
| Views and security | 5 More, All Words order, past days, PDF HEAD; foreign `Origin` and `Host` refused |

### Error paths

| Case | Result |
|---|---|
| Wrong OpenAI key | "The LLM provider rejected the API key in .env." in 1.8 s |
| Unknown OpenAI model | "…does not know the model openai/no-such-model…" in 1.4 s |
| Groq daily limit (live) | Its own message in 0.7 s |
| Wrong Groq key, unknown Groq model, wrong Guardian key | Checked in the first run of this round, on the old code: right messages in 0.6 s, 0.6 s and 4.0 s, nothing stored. These paths were not changed by the fixes |

### Browser (Chromium, gpt-4o-mini)

- **During an Edit:** feedback, Edit, Accept and Delete were all disabled.
  Afterwards they were enabled again, and all 3 quotes were still there.
- **During and after Accept:**
  - The footer was locked while Accept ran.
  - Afterwards the "Accepted" note showed. Edit and Accept stayed disabled,
    and Delete stayed enabled.
  - A cancelled Delete restored the footer.
- **Console:** 0 errors.
- **Search and cards:** accent-insensitive search worked, and no card title
  overlapped its badge.

## Observations

- **Speed.** gpt-4o-mini served 12 concurrent opens in 5.8 s, with no retries.
  Groq's free tier took 81 s for 8, near its 90 s retry budget, and its
  200,000-token daily allowance ran out during testing (twice, counting the
  earlier run that day).
- **Pronunciation quality** is similar on both models, and imperfect. Both got
  "raison d'état" wrong. This is in the README limitations.
- **Not run:** the gated quote rule on Groq (its daily allowance was used up),
  and a live wrong-Groq-key run after the fixes (the code path is unchanged).
