# Debug report

Word Bank (renamed from Word Hoard), 5 October 2026. Covers the third code review
(`REVIEW.md`, written at `a45a44e`), the bugs found by testing with **real Groq and
Guardian calls**, the fixes, and the end-to-end retest.

## How it was tested

- **Reproduce first.** Every finding was reproduced before anything was decided:
  probes through the test fixtures, direct inspection, a real browser, or real
  API calls.
- **Real services.** The LLM was Groq (`groq/openai/gpt-oss-120b`, from `.env`)
  and The Guardian Open Platform. Keys were loaded with
  `uv run --env-file .env`; none were copied or printed.
- **Real data protected.** Every server run used a scratch copy of the code
  with its own copy of `data/` and `output/`. The real files are unchanged
  from `HEAD`.
- **Regression tests.** Each fix has one, and each was run against the unfixed
  code to show it detects the bug.

## Bugs found only with real calls

These did not show up in the 87 offline tests. They appeared as soon as Groq and
The Guardian were really called.

### 1. Groq's per-minute limit made normal use fail

**Symptom.** Opening one new entry three times at once returned "The LLM service
failed. Try again in a minute." for the first request.

**Root cause.** Groq's on-demand tier limits this model to 8,000 tokens per
minute. One detail request uses about 1,500–1,600 tokens, so a handful of opened
entries reaches the cap. Groq's own error message says it:

```
RateLimitError: Rate limit reached for model `openai/gpt-oss-120b` ... on tokens per minute (TPM):
Limit 8000, Used 6899, Requested 1599. Please try again in 3.735s.
```

The app retried 4 times, waiting 2, 4 and 8 s: 14 s in all, against a limit
measured over 60 s. Groq also returned one `ServiceUnavailableError` ("over
capacity"). litellm does not pass Groq's `retry-after` header on
(`error.response.headers` had none), so the wait cannot be read from the
response. It appears only in the message text.

**Fix (`llm.py`).** Exponential backoff capped at 20 s, stopping after 90 s
(`RETRY_SECONDS`) or 8 attempts (`MAX_ATTEMPTS`). A rate-limited attempt is
refused in about 0.1 s and uses no tokens, so the extra attempts cost nothing.
A fake-clock test proves a one-minute limit is waited out, and that a limit
that never lifts gives up within the budget. The old policy fails the first
test.

**Real result.** Two full end-to-end runs absorbed 26 and 18 failed attempts
with no error reaching the user (0 × 502). The busiest steps took 20–40 s
instead of failing.

### 2. A wrong Groq key was retried for 74 s, then misreported

**Symptom.** With a wrong `GROQ_API_KEY`, opening an entry took **74.2 s** and
then said "The LLM service failed. Try again in a minute." The intended message
is "The LLM provider rejected the API key in .env.", given at once.

**Root cause.** litellm reports Groq's 401 as a `BadRequestError` carrying
`status_code` 401, not as an `AuthenticationError`. Both the "do not retry"
rule and the server's message were keyed on the exception class:

```
litellm.exceptions BadRequestError | status: 401
isinstance litellm.AuthenticationError: False
GroqException - {"error":{"message":"Invalid API Key","code":"invalid_api_key"}}
```

**Fix.**
- `llm.worth_retrying` judges by HTTP status: 401, 403 and 404 are permanent,
  and so are non-`Exception` errors such as `KeyboardInterrupt`.
- `server.llm_failed` picks its message from the same status, replacing two
  class-based handlers.
- Tests reproduce Groq's exact error shape; they fail on the old code.

**Real result.** A wrong Groq key now gets the right message in **0.6 s**. A
wrong Guardian key gets "The Guardian rejected GUARDIAN_API_KEY. Check it in
.env." in 6.7 s. Neither stores an empty detail.

### 3. Guardian footers glued onto quotes

**Symptom.** "mum's the word" was shown the quote "Mum's the word! • Anthony
Watt writes a regular blog for SocietyGuardian.co.uk on his experiences of
being an adoptive father."

**Root cause.** The Guardian puts a "•" bullet before author notes and
reader-letter footers. The sentence splitter only broke at . ! ? followed by a
capital, so the footer stayed attached. In real searches, 2 of 44 candidates
were affected; the other was "Kathleen Askew Hayling Island, Hampshire • Have
an opinion on anything you've read in the Guardian today?"

**Fix (`guardian.py`).** A bullet is also a sentence boundary. The fragments it
separates are under 8 words, so the length rule drops them. Real searches now
return 0 such candidates, and a test covers it.

## Review findings

| # | Finding | Verdict | Evidence |
|---|---|---|---|
| H1 | Concurrent accepts lose an entry or blame a PDF viewer | **Genuine, fixed** | Two parallel accepts: one refused with "vocabulary.pdf is open in another program" though nothing was open |
| H2 | A malformed Guardian date blocks PDF builds | Not fixed | Unreachable: dates come from the API, and quotes cannot be edited (revise keeps them by number) |
| H3 | Deleted `vocab.db` not recreated | **Genuine, fixed** | `OperationalError: no such table`. A regression from caching the schema in the previous round |
| M1 | Concurrent opens of one entry pay several times | **Genuine, fixed** | 3 parallel opens → 3 `entry_detail` calls |
| M2 | `PAGE_LOCK` held across the LLM call | Not a bug | It is what stops the daily pick running twice |
| M3 | `/api/accepted` sends full details | Not a bug | Loopback-only; fine at current size |
| M4 | `openai` imported but not declared | **Genuine, fixed** | Declared. The review's alternative, `litellm.APIError`, would not catch litellm's errors |
| M5 | No linter | Checked | `ruff check`: style only (import order, nested `with`, naive `date.today()`, which is intended) |
| M6 | Progress data tracked in git | Owner's decision | Unchanged |
| L1 | `start.sh` not executable | **Genuine, fixed** | `100644` → `100755` |
| L2 | Empty pool still calls the LLM | **Genuine, fixed** | One paid call with a bare `Entries:` prompt |
| L3 | No temperature | Not fixed | No evidence it reduces retries |
| L4 | "5 more words added" hardcoded | **Genuine, fixed** | Toast reports the real count; an exhausted list is refused |
| L5 | PDF popup blocked | Not reproduced | Opens in Chromium |
| L6 | Drawer not a dialog; focus escapes | **Genuine, fixed** | Tab reached the *closed* drawer's hidden Close button, and left the open drawer |
| L7 | Double Enter sends two adds | **Genuine, fixed** | Two `POST /api/today/add` in the server log |
| L8–L10 | Orphan rows, `restore` order, `to_dict` key order | Not bugs | Inert, harmless, or unreachable |
| L11 | No split before a digit | **Genuine, fixed** | `"…1984. 2001 was…"` stayed one sentence |
| L12 | First-word placeholders ignored | **False** | Already fixed in `cfce446`, and tested |
| L13, L14, L17 | Day validation, `nosniff`, import side effects | Not bugs | Parameterised SQL; typed JSON; README says to copy the whole folder |
| L15 | Stale artifacts | Cleaned | Probe bytecode removed |
| L16 | `detail` reads twice | Addressed | Restructured for M1, with a comment |

## Fixes (all)

- **`llm.py`**: a retry budget that outlasts Groq's per-minute limit, and
  permanent errors judged by HTTP status.
- **`server.py`**: one LLM error handler, choosing its message by status.
- **`journal.py`**
  - `COLLECTION_LOCK` serialises accept and delete.
  - `DETAIL_LOCKS` give one lock per entry, so a detail is generated once.
  - No LLM call when nothing is left to pick.
- **`db.py`**: the schema runs on each connection (+0.09 ms), so a deleted
  database is recreated.
- **`guardian.py`**: sentences also split before a digit and at "•" bullets.
- **`static/`**
  - The drawer is a modal dialog: `inert` while closed, and the page behind it
    `inert` while open.
  - The add box ignores Enter while busy.
  - The "5 More" toast shows the real count.
- **`pyproject.toml`**: `openai` is declared. **`start.sh`**: executable.
- **Rename**: Word Hoard → Word Bank in the page title and header, the PDF
  (title, title page, footer), the start scripts, README and CLAUDE.md. The
  vocabulary entry "hoard" is unchanged. The existing `output/vocabulary.pdf`
  keeps the old title until the next Accept or Delete rebuilds it.

## Retest results

### Automated

`uv run pytest`: **91 passed** (82 before this round). Every new test fails on
the code before its fix.

### End to end with real Groq and Guardian calls

25 checks over HTTP against the scratch-copy server, all passing on the final
code.

| Check | Result |
|---|---|
| Daily pick | 5 real cards in 4.3 s; IPA, respelling and meaning well formed; no pronunciation for phrases over two words |
| Second load | Does not pick again |
| Details | 3 genuine Guardian quotes each (URL, ISO date, the entry in the text), then written examples, at most 5 |
| 3 concurrent opens of one entry | One identical detail, generated once |
| Typed entries with apostrophes | "a baker's dozen" and "one's bark is worse than one's bite" get real quotes, e.g. "the president's bark is worse than his bite" |
| Typed non-master entry | "zeitgeist" gets real quotes |
| Refusals | Case variant and blank entry refused with clear messages |
| Revise | Quotes kept verbatim, feedback applied (shorter meaning, one example fewer); empty feedback refused |
| Two simultaneous accepts | Both succeed; both are in the PDF, titled Word Bank; both left the word list; accepting again is refused |
| "5 More" | Adds five real entries |
| Delete | A typed non-master entry is removed and not added to the list; a master entry returns to the list and leaves the PDF |
| All Words and past days | All Words is alphabetical; a past day shows only accepted entries |
| Server log | 0 × 502, 0 tracebacks; the only 400s were the deliberate refusals |

### Browser, real calls (Chromium)

- The page is titled Word Bank, with "Word·Bank" in the header.
- **Open:** clicking "mum's the word" filled the drawer with a real
  definition, Guardian quotes linked to their articles, and written examples.
  This is where bug 3 showed up.
- **Edit:** "Drop the second Guardian quote." removed exactly that quote and
  kept the other word for word.
- **Accept:** the toast appeared, the "Accepted" note showed, Edit greyed out
  and the card got its badge.
- **PDF:** opened in a new tab, titled Word Bank, with all 5 accepted entries
  and 13 Guardian links.
- **Keyboard:** the closed drawer is unreachable; the open drawer keeps Tab
  inside it; Escape restores the page and focus.
- **Add box:** a double Enter sends one request.
- **Empty list:** "5 More" shows the refusal and adds nothing.

### Other checks

- `config.missing_settings()` is empty for `.env`.
- `build_vocab.py`: 3500/3500 words, 1500/1500 phrases.
- `data/` and `output/` are unchanged from `HEAD`.

## Observations, not fixed

- **LLM pronunciation quality.** One card gave "au contraire" the
  General-American /oʊ/, although the prompt asks for Received Pronunciation.
  The README already lists pronunciations as a known limitation, correctable
  with Edit.
- **Guardian candidates.** Placeholders and names still let in a few
  irrelevant ones, e.g. "Kathleen Askew" for "askew". The LLM quote chooser
  rejected them in every run.
- **Retry cost under contention.** If generation fails for an entry, each
  request waiting on its lock tries again in turn. With the longer retry
  budget this did not happen in the real runs.

## Remaining risks

- **PDF rebuild time.** Every accept, and every delete of an accepted entry,
  rebuilds the whole PDF: about 13 s at 1,500 entries, 55 s at 5,000. A second
  accept waits for the first.
- **Groq free tier.** Bursts of new entries can pause for up to a minute (now
  in the README). A paid tier, or a smaller model in `LLM_MODEL`, would remove
  the pauses.
- **Progress data in git.** A checkout of an older commit replaces your
  progress.
