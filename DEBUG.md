# Debug report

Word Bank, 5 October 2026. This report covers three things:

- the fourth review's defects and their fixes (REVIEW.md);
- the Groq-first, OpenAI-fallback design that replaced waiting out Groq's
  limits;
- the end-to-end retests.

The last section lists the system's limitations, why each arises, and what could
solve it.

## How it was tested

- **Reproduce first.** Each defect was reproduced, and its root cause shown,
  before it was fixed. Each got a regression test, which failed on the unfixed
  code. The one exception is the blank-key test, which needs a function that
  the fix introduces. That bug was shown directly instead, by loading `.env`
  the old way and the new way.
- **Real services.** Groq (`groq/openai/gpt-oss-120b`), OpenAI
  (`openai/gpt-4o-mini`) and The Guardian Open Platform. Keys were loaded with
  `uv run --env-file .env`, and were never printed or copied. For error paths,
  a single setting was overridden in the environment for that run.
- **Real data protected.** Every server ran from a scratch copy with its own
  `data/` and `output/`. The real files are unchanged.
- **Tools.**
  - HTTP checks: a script, `full_e2e.py`, with 41 checks.
  - Quotes: each stored quote was compared word for word with its article,
    fetched again from The Guardian.
  - The page: Chromium, through Playwright.
  - PDF text: `pypdf`, run with `uv run --with`, so it is not a project
    dependency.

## The LLM design: Groq first, OpenAI at once on failure

### Why it changed

The old policy waited Groq's limits out: it retried for up to 90 s with
exponential backoff. That made the app unpredictable in three ways:

| Behaviour | Measured |
|---|---|
| Unpredictable delay | A panel took anywhere from 2 s to 81 s while Groq's per-minute limit (8,000 tokens) lasted |
| Unpredictable failure | Groq's daily allowance (200,000 tokens) ran out twice during testing. After that, every call failed after 74 s of useless retries |
| Hidden retries | litellm passes `max_retries` to the OpenAI SDK, which by default retries on its own, honouring `retry-after` |

### What it does now (`llm.ask`)

1. Every call goes to Groq once, with a 30 s timeout.
2. If Groq refuses or fails, the same call goes to `LLM_FALLBACK_MODEL`
   (default `openai/gpt-4o-mini`, 60 s timeout) at once. That covers a rate
   limit, the daily allowance, an outage, a timeout, a reply that isn't valid
   JSON, and a reply whose content is wrong (wrong card count, or numbers out
   of range). Each switch logs one line with Groq's reason.
3. A setup mistake is reported and never hidden by the fallback: HTTP 401, 403
   or 404 from either provider. The message names the provider: "The groq
   provider rejected its API key in .env."
4. `max_retries=0` on every call, so the only retries are the app's own. There
   are 3 attempts, with 1 s and 2 s between them, and each attempt starts with
   Groq again.
5. At startup, keys for both models must be present and not blank.

### Measured behaviour (live)

| Situation | Result |
|---|---|
| Groq answers | 1.5 s for a card batch; OpenAI not called |
| Groq's daily limit reached | Refusal in **0.51 s**, then OpenAI; full test 41/41, 39 switches, 0 errors |
| Groq's per-minute limit, 12 concurrent opens | Slowest 6.1 s, against 81 s under the old policy |
| Groq unreachable (closed port) | Switched; 4.7 s in total |
| Groq accepts but never answers (silent socket) | Switched after the 30 s timeout; 32.4 s in total |
| Wrong Groq key | "The groq provider rejected its API key in .env." in 0.6 s; no switch |
| Wrong OpenAI key, Groq answering | Groq answered (2.5 s); the bad key went unnoticed |
| Wrong OpenAI key, Groq unreachable | "The openai provider rejected its API key in .env." in 3.9 s |
| Unknown fallback model | "The openai provider does not know the model no-such-model…" in 1.9 s |
| `OPENAI_API_KEY` missing at startup | "Add these settings to the .env file, then start again: OPENAI_API_KEY"; exit 1 |

### Worst case, by design

| Case | Time |
|---|---|
| Groq refuses | +0.5 s |
| Groq hangs | +30 s |
| Groq and OpenAI both refuse | Error after about 3 × (0.5 s + OpenAI's refusal) + 3 s |
| Both hang (theoretical) | 3 × (30 + 60) + 3 = 273 s, then an error. Not observed |

### Bug found while building it

**Symptom.** A reply from Groq that was valid JSON but wrong in content (for
example 1 card for 2 entries) was retried on Groq, not sent to OpenAI.

**Root cause.** The content checks ran in the public functions, after `ask`
had returned, so `ask` never saw them as a Groq failure.

**Fix.** `ask(prompt, schema, valid=...)` checks the content inside each model
attempt. `test_primary_reply_with_wrong_content_switches_to_fallback` failed
before the fix.

## Fourth-review defects (details in REVIEW.md)

| # | Defect | Proof before | Proof after |
|---|---|---|---|
| H1 | Edit deleted Guardian quotes unasked | Groq 7 of 24 revisions; gpt-4o-mini 3 of 12; ungated `drop_quotes` 4 of 33 | Gated: 0 of 33 unrelated revisions lost a quote; 12 of 12 requested removals exact; end to end, 0 of 9 lost a quote, twice |
| H2 | Edit raced Accept and Delete | Accept during an Edit: the database had the revised meaning, the PDF the old one | Edit refused with "already accepted"; database and PDF agree; the drawer footer is locked while one action runs |
| M1 | Closing quote mark cut off | `…crime.` instead of `…crime.”` in 2 of 30 quotes | 101 stored quotes from three runs checked word for word: 0 problems |
| M2 | Groq daily limit retried for 74 s, wrong message | Measured | Superseded by the fallback: OpenAI answers instead |
| L1 | Blank key passed the startup check | `GROQ_API_KEY=` gave `missing_keys: []` | Named at startup |
| L2 | Search not accent-insensitive | "etat" found nothing | Found |
| L3 | Card title overlapped by the badge | Button 258 px wide in a 229 px card | 20 cards: no overlap or overflow |

## Retest results

- **Automated:** `uv run pytest`: **108 passed** (91 at the start of this
  round). They make no API calls and leave the real data untouched.
- **End to end, Groq first and OpenAI as fallback:** 41 of 41 checks passed,
  twice. Both runs had 0 tracebacks and 0 × 5xx; every 4xx was a deliberate
  refusal. The checks covered:
  - daily pick, typed entries and refusals;
  - concurrent opens;
  - quote keeping and removal;
  - Accept and Delete during an Edit;
  - Accept, the PDF, and the locked PDF;
  - delete rules, 5 More, views, and local-only access.
- **Browser (Chromium):**
  - The footer locks during Edit and Accept, and is restored afterwards. A
    cancelled Delete restores it.
  - Quotes survived an unrelated Edit.
  - Search ignores accents.
  - No card overlaps its badge.
  - 0 console errors.

## Limitations: why they arise, and possible solutions

| Limitation | Why it arises | Possible solution |
|---|---|---|
| Pronunciations, spellings and definitions are sometimes wrong (both got "raison d'état" wrong; "savory" appeared) | Generated by the model, not looked up | Take IPA from a dictionary source; keep Edit for corrections |
| Entries may be written by two models on one day | The fallback writes whatever Groq could not | Use one model (`LLM_MODEL=openai/gpt-4o-mini`), or a paid Groq tier |
| Quote removal by Edit depends on the model's yes/no judgement | Free-text feedback has to be interpreted. Measured 0/33 and 12/12 on gpt-4o-mini; not yet measured on Groq | A per-quote remove button, so no model is involved |
| OpenAI costs money once Groq's free tier is used up | Groq allows 8,000 tokens a minute and 200,000 a day; one full test run used the day's allowance | A paid Groq tier, or an OpenAI spending limit |
| A bad OpenAI key is noticed only when the fallback is first needed | Startup checks presence, not validity, to avoid a paid call and a network dependency at startup | A test request to both providers at startup that refuses only on 401/403/404 |
| A hanging Groq adds up to 30 s | The timeout must allow Groq's slowest normal answers (under 10 s observed) | Shorter timeout, at the cost of abandoning some slow but valid answers |
| A new entry cannot be opened while The Guardian is unavailable | Detail generation is one step; a Guardian failure fails it, and quotes have no fallback | Store the detail without quotes and add quotes on a later open |
| Some entries have fewer than 3 quotes, or off-topic candidates ("Kathleen Askew") | The Guardian may rarely use the entry; its search matches names | Written examples fill gaps; the model's chooser rejected names in every run |
| Accept and Delete slow down as the collection grows (13 s at 1,500, 55 s at 5,000) | The whole PDF is rebuilt in two passes for the contents page, under one lock | Background or sectional rebuilds |
| If every attempt on both models returns a wrong reply, the page shows a generic "Server error 500" | The final `ValueError` has no message mapping. It needs 6 wrong replies in a row, and was never seen | Map it to a readable message if it ever occurs |
| Audio reads foreign phrases as English | The browser's built-in en-GB voice | A voice per language, or a text-to-speech service |
| Single user, this computer only | Requests from other hosts and origins are refused; there are no accounts | Accounts, a database server and hosting |
| Checking out an older commit replaces progress | Progress files are tracked in git | Back up `data/` first, or move progress out of git |
