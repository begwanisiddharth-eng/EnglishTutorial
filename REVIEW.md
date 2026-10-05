# Code review: Word Hoard

Reviewed on 5 October 2026, at `a45a44e` (four commits). 51 tracked files.

This supersedes the review at `36925de`. Every high-severity finding in that
review has been fixed, and the 82-test suite added in `cfce446` and `a45a44e` is
a genuine improvement — the second round of fixes has regression tests for each
one. What follows is a fresh look at the current code.

## Scope and method

Read every source file (`server.py`, `journal.py`, `db.py`, `llm.py`,
`guardian.py`, `vocab.py`, `pdf.py`, `config.py`, `build_vocab.py`,
`static/index.html`, `static/app.js`, `static/style.css`), all eight test
modules, `README.md`, `CLAUDE.md`, `pyproject.toml`, `.gitignore` and the start
scripts, plus `uv.lock` and the `parts/` tree.

`.env` was not read. `config` was imported, which loads it, so the module
imports and `missing_settings()` could be checked; no value was printed.

To avoid touching real progress, every experiment ran against **copies** of the
modules in a temp directory with their own `data/`, `output/` and `fonts/`, with
`llm.completion` and `guardian.search` replaced. `data/vocab.db` was opened once,
read-only, with `sqlite3.connect("file:...?mode=ro", uri=True)`. No LLM or
Guardian call was made. The server was never started and the browser never
opened. No tracked file was modified apart from writing this review.

Things I ran rather than guessed:

| Check | Result |
|---|---|
| `uv run pytest` | 82 passed in 5.4 s (db 3, guardian 20, journal 25, llm 6, pdf 8, server 13, vocab 7) |
| `uv run build_vocab.py` | 3500/3500 words, 1500/1500 phrases, 0 duplicates, 0 words with spaces |
| `VOCABBASE.TXT` vs `parts/` | same 5,000 entries; each section sorted by `vocab.fold`; unique by fold; no blank lines |
| Word/phrase boundary | line 3500 is `zephyr` / `a babe in the woods`, matching `vocab.WORD_COUNT` |
| `remaining.txt` vs the database | 4,997 entries = 5,000 − 3 accepted, and the three missing are exactly the three accepted. Consistent |
| Two accepts at once | **accepted in the database: `['abase', 'abash']`; present in the PDF: `['abash']`** (H1) |
| Two accepts that collide on the temp file | one refused with *"vocabulary.pdf is open in another program"*; nothing was open (H1) |
| One Guardian date changed to `2025-13-45` | `ValueError` out of `pdf.build`; old PDF bytes unchanged; no recovery route (H2) |
| `data/vocab.db` deleted while the process runs | `OperationalError: no such table: days` on every query (H3) |
| Three concurrent requests for one entry's detail | 3 paid `entry_detail` calls, 3 Guardian searches (M1) |
| A second "5 More" during one card generation | blocked for the full duration; worst case 120 s × 4 attempts (M2) |
| `/api/accepted` at 3,000 entries | **3.7 MiB** of JSON, ~170 KiB of it used by the page (M3) |
| Empty vocabulary pool | one paid LLM call with a prompt ending in a bare `Entries:` (L2) |
| 300-entry PDF build | 1.6 s, on every Accept and every accepted-entry Delete |
| `git ls-files data output` | all three progress files are tracked (M6) |
| `git ls-files -s start.sh` | mode `100644` — not executable (L1) |
| `server.py` imports | `openai` is imported but not declared in `pyproject.toml` (M4) |

Severity is about consequence for this app specifically: a single-user, local,
personal tool whose most precious asset is a few years of accumulated progress.

## Findings

### High

**H1. Two accepts at the same time can leave an accepted entry out of the PDF
permanently.**

`journal.accept` (`journal.py:140`) takes no lock, and FastAPI runs these `def`
endpoints in a threadpool, so two accepts genuinely run at once — two browser
tabs, or accept while an earlier accept is still building. Each thread computes
its own `db.accepted_entries() + [self]` list, then both write to the **same**
`pdf.TEMP_PATH` (`pdf.py:21`, `pdf.py:168`).

Two outcomes, both reproduced:

*Both builds complete.* The last `TEMP_PATH.replace()` wins, so the PDF holds
only one of the two entries while both rows are marked accepted and both have
been dropped from `remaining.txt`:

```
accepted in the database: ['abase', 'abash']
present in the PDF:       ['abash']
in the database but missing from the PDF: ['abase']
remaining.txt: []
```

`journal.delete` on an accepted entry has the mirror-image problem. There is no
route that rebuilds the PDF from the database, so the only accidental recovery is
to accept some other entry, which rebuilds from `db.accepted_entries()`.

*The builds collide.* On Windows the losing thread's `replace` raises
`PermissionError`, which `journal.publish_pdf` (`journal.py:136`) reports as
**"vocabulary.pdf is open in another program. Close it and try again."** Nothing
is open. The user is sent to hunt for a PDF viewer that does not exist.

The fix is small: hold `PAGE_LOCK` across the whole of `accept` and of
`delete`-when-accepted, and give each build its own temp filename. That removes
both the lost entry and the misleading message.

**H2. One malformed Guardian date makes the collection permanently
un-exportable.**

`pdf.source_line` (`pdf.py:111`) calls `date.fromisoformat(example["date"])` with
no fallback. Changing one stored example to `date: "2025-13-45"` gives:

```
build raised ValueError: month must be in 1..12
old PDF preserved: True
```

The temp-file swap added in `a45a44e` does its job — the existing PDF is
untouched. But from that point on **every** accept and every accepted-entry
delete raises, so nothing can be added to or removed from the collection, and
no route rebuilds the PDF. The only way out is editing SQLite by hand.

`publish_pdf` catches `PermissionError` and nothing else. Catching
`(KeyError, ValueError)` alongside it, and falling back to the raw string for the
date, closes this at both ends. Note the risk is low today — Guardian dates are
sliced to `YYYY-MM-DD` at `guardian.py:101`, and I checked all 3 real Guardian
quotes in `data/vocab.db` and every one parses — but the consequence is
proportional to the collection size, so the guard is worth having.

**H3. `db.create_schema` is `@cache`d, so a deleted database file is never
recreated.**

`db.create_schema` (`db.py:25`) caches on the path, so the DDL runs once per
process per path. Delete `data/vocab.db` while the app is running and every
query fails for the rest of the session:

```
cache info: CacheInfo(hits=1, misses=1, currsize=1)
OperationalError: no such table: days
```

That includes `GET /api/today`, so the app looks dead until it is restarted.
Low probability, but the same caching would block any future schema migration,
which is the more likely reason to hit it.

### Medium

**M1. One drawer open can cost three paid LLM calls and three Guardian searches.**

`journal.detail` (`journal.py:102`) reads, generates and writes with no lock.
Three concurrent requests for the same entry produced three `entry_detail`
calls:

```
entry_detail calls for one entry: 3
```

Each one is a paid LLM call plus a Guardian search (CLAUDE.md warns that detail
generation makes several). A double-click, a retry after a slow response, or two
tabs will all do it. A per-entry lock, or a sentinel row written before
generating, would make it once.

**M2. `PAGE_LOCK` is held across the network call.**

`todays_entries`, `add_random` and `add_typed` (`journal.py:38`, `journal.py:45`,
`journal.py:71`) hold `PAGE_LOCK` around `llm.card_summaries`. A second request
waits for the whole first one:

```
'5 More Words' waited 0.66s behind one card generation
the real limit is TIMEOUT_SECONDS x attempts: 120 x 4
```

So a hanging provider can block the Today page for up to eight minutes. The
lock is only needed for the check-then-insert, but releasing it before the LLM
call would let two requests pick the same words — so the honest options are to
reserve the pick first and generate afterwards, or to keep the lock and give
card generation a much shorter timeout than detail generation. Worth deciding
deliberately rather than inheriting.

**M3. `/api/accepted` ships everything for a list that uses four fields.**

`db.accepted_entries` (`db.py:78`) selects `*` and returns full details;
`renderList` (`static/app.js:249`) reads only `id`, `entry`, `meaning` and `day`.
At 3,000 accepted entries:

```
query time: 55 ms
JSON the browser downloads and parses: 3.7 MiB
the fields the list actually uses: ~170 KiB
renderList builds 3000 DOM rows on every keystroke in the search box
```

The full payload is also kept in the `known` Map for the whole session. A
`SELECT entry, day, card` variant behind the same route, or a second
`/api/accepted?summary=1`, would cut roughly 95% of it. `renderList` rebuilding
every row per keystroke is the other half; `requestAnimationFrame`-throttling
the `oninput` handler would cover it.

**M4. `openai` is imported but never declared.**

`server.py:9` imports `openai` and `server.py:97` catches `openai.APIError`. It
appears in `uv.lock` only because litellm happens to depend on it. Declare it in
`[project] dependencies` or catch `litellm.APIError` instead.

**M5. No linter.**

CLAUDE.md states this plainly. `ruff` would cost nothing to add and would keep
the one-line-docstring-per-function style honest; it would also have caught the
unused locals my probes left behind in two places.

**M6. Progress data is tracked in git.**

`git ls-files` confirms `data/vocab.db`, `data/remaining.txt` and
`output/vocabulary.pdf` are all tracked. `output/vocabulary.pdf` is fully
rebuildable from the database and has no business in version control. As it
stands, a `git checkout`, a `git restore`, or a clone of an older commit silently
replaces real progress with no warning and no conflict marker.

To be fair to the current setup: I verified the three are currently consistent
— 4,997 remaining against 5,000 minus 3 accepted, and the three absent entries
are exactly the three accepted ones. So it is working as a backup today. I would
still take the PDF out and keep dated copies of `vocab.db` outside the repo.

### Low

**L1. `start.sh` is not executable.** `git ls-files -s start.sh` returns mode
`100644`. README line 27 tells Mac/Linux users to run `./start.sh`, which fails
with "Permission denied" on a fresh clone. Either `chmod +x` and commit mode
`100755`, or write `sh start.sh` in the README.

**L2. An exhausted vocabulary list still calls the LLM.** `vocab.pick` returns
`[]` when the pool is empty and `pick_into` (`journal.py:31`) hands that straight
to `card_summaries([])`. Verified: one paid call whose prompt ends in a bare
`Entries:`. Return early when there is nothing to pick.

**L3. `llm.ask` sets no temperature** (`llm.py:126`). Non-determinism is what
makes the count-mismatch retries fire, and each retry costs another full batch
call. `card_summaries` also discards a whole batch when the count is off by one
(`llm.py:153`); zipping what came back and retrying only the shortfall would be
cheaper than starting over.

**L4. "5 More Words" always says five.** `generateMore`
(`static/app.js:181`) hardcodes "5" in the toast although the server uses
`journal.DAILY_COUNT`, and it cannot add fewer than five even when only two
unaccepted entries remain.

**L5. `openPdf` can be silently blocked as a popup.** `window.open` runs after
an `await fetch` (`static/app.js:415`), which loses the user-gesture context in
some browsers; the button then does nothing at all. `window.location.href =
"/api/pdf"` is never blocked.

**L6. The drawer is not a dialog.** `<aside class="drawer">`
(`static/index.html:76`) has no `role="dialog"`, no `aria-modal` and no
`aria-labelledby`, and focus is not trapped — Tab walks out of the open drawer
into the page behind it. Escape and focus restoration are already handled well
(`static/app.js:374`), so only the semantics and the trap are missing.

**L7. The add box stays live during its request.** `withSpinner` disables
`#add-btn`, but the Enter handler (`static/index.html:32`) bypasses it, so a
double Enter fires two `/api/today/add` calls. The second is refused with
"already on today's page", which reads as a failure of the word just added.

**L8. Orphaned rows accumulate.** An unaccepted row from a past day can never
be accepted, revised or opened: `editable` refuses it and Browse hides it.
There are 8 such rows from 2026-10-04 in the real database. They stay in
`remaining.txt`, so the same word can correctly reappear on a later day
(verified), but the dead rows are never cleaned up. A
`DELETE FROM entries WHERE accepted = 0 AND day < ?` at startup would tidy it.

**L9. `vocab.restore` appends, so `remaining.txt` drifts out of the master's
order,** and it does an O(n) list scan per candidate (`vocab.py:68`) — about
21 ms measured at 5,000 entries. Harmless, because the file is only ever
sampled at random, but a set would be both faster and clearer.

**L10. `db.to_dict` puts the card fields last** (`db.py:46`), so a card JSON
containing `id`, `day`, `accepted` or `detail` would silently override the real
columns. `insert_cards` and `update_card` both strip `entry`, so it cannot
happen today — but the ordering makes it one careless change away, and a
`TypeError` on unexpected keys would surface it immediately.

**L11. `guardian.SENTENCE_END` will not split before a digit.** Verified:

```python
guardian.SENTENCE_END.split("The year 1984. 2001 was also a turning point for the archive.")
# ['The year 1984. 2001 was also a turning point for the archive.']
```

Two sentences arrive as one, so the quote the learner sees has a full stop in the
middle of it.

**L12. `guardian.entry_pattern` still ignores `PLACEHOLDERS` for the first
word** (`guardian.py:72`), so a future entry beginning "someone's" or "oneself"
would be matched literally. Harmless for all 5,000 current entries — the leading
"one's" in the two phrases concerned is literal anyway.

**L13. `/api/days/{day}` accepts any string.** A malformed day returns `[]`,
which the page renders as "No accepted entries on this day." Validating with
`date.fromisoformat` would turn a typo into a clear 400.

**L14. No response hardening headers.** `no_cache` (`server.py:55`) sets only
`Cache-Control`. `X-Content-Type-Options: nosniff` is one line and stops a
browser treating a JSON error body as HTML. A CSP would need the inline
`onclick` handlers relaxed first, so it is a later job.

**L15. Stale artifacts.** `tests/__pycache__/` holds `test_probe` and
`test_probe_review` `.pyc` files whose sources are gone.
`.playwright-mcp/` is 32 files / 416 KB of browser snapshots — gitignored, safe
to delete. `.pytest_cache/` is not in `.gitignore` and only stays invisible
because of its own internal `.gitignore`.

**L16. `journal.detail` reads the row twice** (`journal.py:105-107`): once to
check, once after writing, and the second read is what it returns. Correct, but
it looks redundant enough to invite a "cleanup" that would return the freshly
built dict instead of the stored one. A comment would help.

**L17. Import-time side effects make a partial copy fail opaquely.**
`pdf.py:32` registers fonts at import and `server.py:27` mounts `static/` at
import, so importing either module without its data directory raises a
reportlab `TTFError` or a Starlette `RuntimeError` rather than saying which
folder is missing. This caught me out during this review.

## Documentation

**README is accurate.** I checked its claims against the code: the 5,000 /
3,500 / 1,500 counts against `build_vocab` output and `VOCABBASE.TXT`; the PDF
layout against `pdf.build`; the read-only past-day rule against
`journal.editable`; the "Guardian quotes first" ordering against
`journal.build_detail`; the audio button against `speak`; and the file table
against the tree. Two gaps: it does not say the daily pick happens on the first
page load of the day (CLAUDE.md does), and it does not mention that
`DAILY_COUNT` and `MAX_EXAMPLES` are constants in `journal.py`.

**CLAUDE.md is accurate**, including the layering and the 3,500-line boundary.
One clarification worth making: it says the master list "is read once and
cached", which is true, but `vocab.load_remaining` still re-reads and re-folds
all of `remaining.txt` on every add, accept and delete. Not wrong — just the
thing to know before optimising the wrong function.

**`build_vocab.py`'s own advisory output** contains one false positive:
`possible derived pairs: [('bane', 'banal')]`. "bane" is not the base of
"banal"; it is the suffix heuristic guessing. Advisory output only, and the
script's validation verdict does not depend on it.

## What I would fix first

1. **H1** — one lock across accept and delete-of-accepted, plus a unique temp
   file per build. Removes both the lost entry and the false "open in another
   program".
2. **H2** — fall back to the raw date string; catch `(KeyError, ValueError)` in
   `publish_pdf`.
3. **H3** — drop `@cache` from `create_schema`, or key it on the file existing.
4. **M1, M2** — a per-entry lock for detail generation, and a decision about
   holding `PAGE_LOCK` across the network call.
5. **M3** — a summary variant of `/api/accepted`, and throttle `renderList`.
6. **M6** — take `output/vocabulary.pdf` out of git.
7. **L1-L4** — the executable bit, the empty-pool call, `temperature=0`, and the
   hardcoded "5".

There is no linter and no type checking on the LLM/DB boundary, which is why
items 4 and 7 survived two review rounds. Adding `ruff` to the dev group would
cost one line.

## What I did not do

- Did not read `.env`, so I cannot say which provider keys are configured. I
  did confirm `config.missing_settings()` names a missing provider key correctly
  by monkeypatching it, and that `server.py:181` exits with a readable message.
- Did not start the server or open a browser, so **the front-end findings come
  from reading the three `static/` files, not from observation.** L5, L6 and L7
  in particular are reasoning about browser behaviour and deserve five minutes of
  manual checking.
- Did not make a single LLM or Guardian call, so nothing here says whether the
  prompts produce good output. All probing was done against copies in a temp
  directory with the two network boundaries faked.
- Did not modify any code, and did not touch `data/`, `output/`, `VOCABBASE.TXT`
  or anything else tracked. The only change in the working tree is this file.
