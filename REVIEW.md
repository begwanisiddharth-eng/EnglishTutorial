# Code review: Word Hoard

Reviewed on 5 October 2026. Single commit (`36925de`), 41 tracked files.

## Scope and method

Read every source file (`server.py`, `journal.py`, `db.py`, `llm.py`, `guardian.py`,
`vocab.py`, `pdf.py`, `build_vocab.py`, `static/*`), the README and CLAUDE.md, and
inspected the runtime data (`VOCABBASE.TXT`, `parts/`, `data/`, `output/`).

To avoid touching real progress I copied the modules to a temp directory and
exercised them there, queried `data/vocab.db` read-only (`mode=ro`), and made no
LLM or Guardian calls. `.env` was not opened. No server was started.

Things I checked by running them:

| Check | Result |
|---|---|
| `uv run build_vocab.py` | passes: 3500/3500 words, 1500/1500 phrases, 0 duplicates, 0 words containing spaces |
| `VOCABBASE.TXT` boundary at line 3500 | `zephyr` / `a babe in the woods` — matches `vocab.WORD_COUNT` |
| `remaining.txt` (4997) vs base (5000) vs 3 accepted rows | consistent, no drift |
| `db.get` / `journal.detail` / `accept` / `delete` with an unknown id | all raise `TypeError` (see H1) |
| `pdf.source_line` with a bad or missing date | `ValueError` / `KeyError` (see H2) |
| `pdf.build` with two identical accepted entries | succeeds, but emits duplicate TOC entries |
| `vocab.is_phrase` cost | ~0.67 ms per call (see M3) |
| All modules import cleanly | yes, except `server.py` without `static/` (see L6) |

## Findings

Severity is about consequence for this app: a single-user, local, personal tool
whose most precious asset is a few years of accumulated progress.

### High

**H1. Any request for a deleted entry id is a 500, and the page shows a JSON
parse error instead of a message.**

`db.get` returns `None` for a missing row (`db.py:80`), and every caller
dereferences it straight away: `journal.py:72`, `journal.py:90`,
`journal.py:101`, `journal.py:111`. Confirmed:

```
db.get(9999) -> None
journal.detail(9999) raises TypeError 'NoneType' object is not subscriptable
```

So the id is only guarded by the front end. A stale tab, a refresh after
deleting an entry from another view, or a hand-typed URL all produce
`Internal Server Error`, and because `app.js:24` parses the body as JSON before
checking the status, the toast reads "Unexpected token '<'" rather than
anything useful. One helper fixes all four sites:

```python
def get_or_refuse(entry_id):
    entry = db.get(entry_id)
    if entry is None:
        raise Refused("That entry no longer exists.")
    return entry
```

**H2. One bad Guardian date makes the whole PDF unbuildable, and a failed build
can destroy the only copy of the collection.**

`pdf.source_line` calls `date.fromisoformat(example["date"])` (`pdf.py:102`).
Guardian dates are sliced to `YYYY-MM-DD` today (`guardian.py:82`), so this works
— but nothing guarantees it keeps working, and any hand-edited or truncated row
raises out of `pdf.build`. Because `pdf.build` rewrites `output/vocabulary.pdf`
in place (`pdf.py:156`) and is called on every accept and every accepted-entry
delete (`journal.py:106`, `journal.py:117`), a failure mid-write leaves a
truncated PDF and every subsequent Accept returns 500 — a state the user cannot
repair through the UI. Three changes together close this:

- build to `vocabulary.pdf.tmp` and `Path.replace()` it only on success;
- parse the date with a fallback to the raw string rather than raising;
- keep the last good PDF until the new one is complete.

**H3. Accept and delete are not atomic across the database, the working list and
the PDF.**

`journal.accept` (`journal.py:100`) marks the row accepted, then edits
`remaining.txt`, then rebuilds the PDF, with no rollback. If the third step
raises, the entry is permanently accepted in the database, has been dropped from
the vocabulary list, and is missing from the PDF. `journal.delete` has the
mirror-image problem. Reorder so the irreversible step comes last: build the new
PDF to a temp file, then commit the row and the list, then swap the file.

### Medium

**M1. The same entry can be accepted twice.**

`journal.add_typed` (`journal.py:47`) rejects duplicates only against today's
page and accepted rows; `vocab.pick` (`vocab.py:25`) excludes only today's
entries. A word shown on Monday and left unaccepted can therefore reappear on
Tuesday, and accepting both days yields two accepted rows with the same text.
`pdf.build` survives it (verified) but prints the word twice, adds two TOC lines
and reuses the bookmark key `f"{level}-{text}"` (`pdf.py:87`), which leaves a
duplicate named destination in the outline. A partial unique index on
`lower(entry)` for accepted rows would make the invariant enforceable in the
database rather than in two different Python code paths.

**M2. Front-end error reporting assumes every response is JSON.**

`app.js:20-27` calls `response.json()` before checking `response.ok`. Every
non-JSON response — FastAPI's plain-text 500, a proxy error, an HTML error page
— becomes a `SyntaxError` and an unintelligible toast. Read the body as text
first and `JSON.parse` inside a `try`.

**M3. `vocab.is_phrase` re-reads and re-scans the master list on every call.**

`vocab.py:36-41` reads all 5000 lines from disk, then does `base.index(entry)`,
and `pdf.build` calls it twice per entry (`pdf.py:153-154`). Measured 0.67 ms per
call, so ~0.7 s of pure classification per rebuild at 500 accepted entries and
proportionally worse beyond that, all of it re-reading the same 64 KB file. Load
the list once into a dict mapping entry to section index.

**M4. Every accept and delete rebuilds the entire PDF.**

`pdf.build` calls `multiBuild` (`pdf.py:156`), which is correct for the linked
contents page but is O(entries) work per user action. Fine for tens of entries,
noticeable in the hundreds. If it ever feels slow, defer the build to
`GET /api/pdf`.

**M5. `db.connect()` per query, and `with conn` treated as a closer.**

`db.py:21-27` opens a connection, re-runs `executescript(SCHEMA)` and is then
used as `with connect() as conn:` in all eleven call sites. `with` on a sqlite3
connection commits or rolls back; it does not close. The connections do get
closed here by CPython refcounting when the local goes out of scope, so this is
not a live leak, but it is misleading and the DDL should not run per query.
Measured 0.78 ms per call. One module-level connection, schema created once.

**M6. Missing or wrong keys surface as `KeyError` and a 500.**

`llm.py:123` reads `os.environ["LLM_MODEL"]` and `guardian.py:78` reads
`os.environ["GUARDIAN_API_KEY"]`. A first-run user with an incomplete `.env`
sees "Internal Server Error" instead of "set GROQ_API_KEY in .env". Validate
both once at startup and turn the result into a readable message.

**M7. Guardian errors are retried indiscriminately and then crash the request.**

`guardian.py:72-73` retries on `urllib.error.URLError`, and `HTTPError` is a
subclass of it — so a 401 from a wrong key burns three attempts with exponential
backoff and then raises an unhandled 500, which is what the user sees when
Guardian quotes fail. Retry transport failures only, and map 4xx to a `Refused`
with the real reason. Worth noting: the free key is rate-limited, and a 429 is
currently indistinguishable from a bad key.

**M8. The app is not keyboard accessible.**

Cards are `<div onclick>` (`app.js:120`), so nothing on the Today or Browse page
can be reached by keyboard. The drawer cannot be closed with Escape, focus is
never moved into it and never restored on close. Using `<button>` for cards and
adding an Escape handler would cover most of it.

### Low

**L1. Case-insensitive matching is ASCII-only in SQLite, Unicode-aware in
Python.** `db.py:68` uses `COLLATE NOCASE` and `db.py:75` uses SQLite `LOWER`,
both of which ignore non-ASCII, while `journal.py:47` uses Python `.lower()`,
which does not. For entries such as "façade" or "ödipus" the two disagree about
what counts as a duplicate.

**L2. `.env` is loaded in one module but read in two.** `load_dotenv` is only
called in `llm.py:11`; `guardian.py` reads the environment without loading it.
This works only because `journal.py` imports `llm` before any Guardian call.
Import or reorder `guardian` on its own and you get a `KeyError`. A small
`config.py` imported by both removes the ordering dependency.

**L3. The placeholder regex never applies to the first word of an entry.**
`guardian.entry_pattern` uses `inflectable` for `words[0]` and `literal` for the
rest (`guardian.py:52-56`), and `PLACEHOLDERS` is only consulted by `literal`.
Verified: "one's bark is worse than one's bite" compiles to
`\bone['’]s\w{0,4}\s+bark…`, not the intended possessive alternation. Harmless for
today's list — the leading "one's" is literal anyway — but the intent silently
breaks for any future entry that starts with a placeholder. Separately,
`inflectable` is crude: `\w{0,4}` plus a word boundary still admits
non-inflections ("tru\w{0,4}" matches "truth" and "truism"), so the LLM chooser in
`llm.choose_quotes` is the only real precision filter.

**L4. The calendar's highlighted dates go stale after accepting.**
`refreshDates` is only called from `initCalendar` (`app.js:180-186`), which runs
on entering Browse. Accepting an entry in Today then switching to Browse shows
the old set until the user leaves and returns.

**L5. A failed first load removes Add and 5 More for the session.** The catch in
`loadToday` (`app.js:148-150`) renders the error into the cards area but leaves
`#today-actions` hidden, so the only way back is a reload.

**L6. Import-time hard dependencies make a partial copy fail opaquely.**
`server.py:21` raises from `StaticFiles` if `static/` is missing, and `pdf.py:32`
registers fonts at import time, so `import server` fails without `fonts/` too.
The README's "copy the whole folder" covers it; one clear check would be kinder
than a Starlette `RuntimeError`.

**L7. `llm.ask` sets no timeout and no temperature** (`llm.py:122-126`).
`temperature=0` would make the count-mismatch retries that each cost another API
call much less frequent.

**L8. `Detail.senses` is unbounded** (`llm.py:90`) while `examples` is capped at
5. A verbose model can produce a detail blob that is large in the revise prompt
and in the PDF.

**L9. The example limit is written twice.** `journal.MAX_EXAMPLES` (`journal.py:11`)
and `Field(max_length=5)` on `Detail.examples` (`llm.py:91`) are the same rule;
`entry_detail` always asks for 5 regardless of `MAX_EXAMPLES`.

**L10. Progress data is tracked in git.** `git ls-files` confirms
`data/vocab.db`, `data/remaining.txt` and `output/vocabulary.pdf` are all tracked,
and all three are currently modified in the working tree. That is fine as a
backup, but it means a `git checkout`, `git restore` or a clone of an old commit
silently replaces real progress. CLAUDE.md flags the risk. I would take the PDF
out of git (it is fully rebuildable from the database) and keep a dated copy of
`vocab.db` outside the repo.

**L11. Local-only server, no origin checks.** Binding to 127.0.0.1
(`server.py:127`) is right. But the bodyless POST routes (`/api/today/more`,
`/api/entries/{id}/accept`) are CORS-simple requests, so any page open in the
default browser can trigger them, and DNS rebinding works because the `Host`
header is never validated. Low impact for a single-user tool; an allow-list of
`Host`/`Origin` closes it entirely.

**L12. Stale artifacts.** `__pycache__/details.cpython-313.pyc` exists with no
`details.py` — a module that was folded into `journal.py` at some point.
`.playwright-mcp/` holds 15 screenshots and console logs from the original build
session; it is gitignored and safe to delete. `pyproject.toml` declares no
development dependencies.

**L13. `build_vocab.PARTS` is CWD-relative** (`build_vocab.py:11`) while every
other module resolves paths from `__file__`, so `uv run build_vocab.py` only
works from the project root. `pdf.py:17` also imports `fold` from
`build_vocab`, coupling PDF generation to the list-building script.

**L14. `/api/pdf` as a plain link.** `index.html:18` is an `<a href="/api/pdf">`,
and before the first accept that route returns `{"error": …}` with status 400
(`server.py:95-96`), so the browser navigates to a page of raw JSON. A button
that fetches and toasts the error would read better.

### Documentation

The README is accurate — I checked every claim against the code, including the
PDF layout, the browse read-only rule, the audio button and the file table. Two
small gaps: it does not say that the daily pick happens on the first page load of
the day (CLAUDE.md does), and it does not mention that the batch size and example
cap are fixed constants.

CLAUDE.md is also accurate. The layering matches, the `Refused` → 400 → toast
path matches `server.py:42-45` and `app.js:25`, and the 3,500-line word/phrase
boundary is real.

One nit in `build_vocab.py`'s own report: `possible derived pairs:
[('bane', 'banal')]` is a false positive of the suffix heuristic — "bane" is not
the base of "banal". Harmless, since it is advisory output only.

## What is worth doing

In order:

1. H1 — one helper in `journal.py`, four call sites.
2. H2/H3 — build the PDF to a temp file, swap on success, commit the database
   last. This is the only finding that can cost real work.
3. M1 — a unique index on accepted `lower(entry)`.
4. M2/M6/M7 — readable errors for bad ids, missing keys and Guardian failures.
5. M3/M5 — cache the master list and the schema; cheap wins.
6. Add `ruff` and a small `pytest` suite over `journal`'s rules with `llm` and
   `guardian` stubbed. There are none today, and the rules in `journal.py` are
   exactly the kind of small, testable logic that benefits most. `journal.py` is
   118 lines and its behaviour is already well described in CLAUDE.md, so a
   dozen tests would cover the whole surface, including the read-only past-day
   rule and the accept/delete round trip through `remaining.txt`.

## Things I did not do

- Did not start the server, so the UI was not exercised in a browser and no LLM
  or Guardian quota was spent. Front-end findings come from reading
  `static/app.js` plus one error captured in a stale Playwright log.
- Did not read `.env`, so I could not confirm which provider keys are actually
  configured.
- Did not modify `data/`, `output/` or any tracked file apart from this review.