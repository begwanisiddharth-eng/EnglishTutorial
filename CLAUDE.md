# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Word Hoard: a local single-user FastAPI app (vanilla JS front end, no build step) that shows advanced English vocabulary entries daily, enriches them with an LLM and real Guardian quotes, and collects accepted entries into a PDF. See README.md for user-facing behaviour.

## Commands

- Run the app: `uv run server.py` (serves http://127.0.0.1:8000 and opens a browser)
- Validate the vocabulary part files: `uv run build_vocab.py`
- Rebuild `VOCABBASE.TXT` from `parts/`: `uv run build_vocab.py --write`
- Run the tests: `uv run pytest`; one test: `uv run pytest tests/test_journal.py::test_accept_removes_from_list_and_builds_pdf`

Tests use temporary data files, a fixed "today" and stubbed LLM calls (`tests/conftest.py`), so they never touch `data/` or spend API quota. The two PDF-lock tests are Windows-only. No linter is configured. The app requires a `.env` with `GROQ_API_KEY` (or `OPENAI_API_KEY`), `GUARDIAN_API_KEY` and `LLM_MODEL` (a LiteLLM model string, e.g. `groq/openai/gpt-oss-120b`).

## Architecture

Layering: `server.py` (thin routes) -> `journal.py` (all business rules) -> `db.py`, `vocab.py`, `llm.py`, `guardian.py`, `pdf.py`. Routes should stay thin; rules belong in `journal.py`. `config.py` loads `.env` once; `server.py` refuses to start if `config.missing_settings()` names anything.

- **Errors shown to the user**: `journal.py` raises `journal.Refused(message)`, which `server.py` turns into HTTP 400 `{"error": message}`. Guardian (`urllib.error`) and LLM (`openai.APIError`, the base of all litellm errors) failures are mapped to 502 with a readable message. `static/app.js` `api()` shows `error` as a toast.
- **Local only**: a middleware refuses requests whose `Host` or `Origin` is not `127.0.0.1:8000`/`localhost:8000`.
- **Entry lifecycle**:
  1. *Card*: on add (daily random pick, "more", or typed), `llm.card_summaries` produces pronunciation, respelling and principal meaning. The daily pick happens lazily on the first `GET /api/today` of a day and is recorded in the `days` table.
  2. *Detail*: generated lazily on first open (`journal.detail`): LLM senses/examples/synonyms plus up to 3 Guardian quotes, quotes first, capped at `MAX_EXAMPLES`.
  3. *Revise*: LLM applies free-text feedback. Guardian quotes are passed by number and can only be kept or dropped, never reworded.
  4. *Accept*: final; rebuilds the PDF, then marks the row accepted and removes the entry from `data/remaining.txt`.
  5. *Delete*: allowed for today's entries or any accepted entry; for an accepted one the PDF is rebuilt first, then the row is deleted and the entry restored to `remaining.txt`.
  The PDF goes first so a failure (typically the file locked by a PDF viewer) leaves nothing changed. Entries are compared with `vocab.fold` (case, accents, œ/æ), so the same entry cannot be accepted twice.
  Past days are read-only and show only accepted entries.
- **Storage** (`db.py`): SQLite `data/vocab.db`. An entry row stores card fields as JSON in `card` and the detail as JSON in `detail`; `to_dict` flattens card fields into the top-level dict. Examples are `{text, source, title, url, date}`; `source: None` marks an LLM-written example.
- **Vocabulary list**: `VOCABBASE.TXT` is the never-modified master list: first 3,500 lines are words, the rest phrases (`vocab.is_phrase` relies on this ordering). `data/remaining.txt` is the working copy of not-yet-accepted entries, created from the master on first run.
- **LLM** (`llm.py`): every call goes through `ask(prompt, schema)` using LiteLLM structured output with a Pydantic `response_format`. Public functions use the `retrying` decorator (tenacity); raising `ValueError` on a bad reply (wrong count, out-of-range numbers) triggers a retry, while `AuthenticationError` and `NotFoundError` are not retried. Guardian retries only network errors, 429 and 5xx. Pronunciation is blanked for entries of more than two words (`make_card`).
- **Guardian** (`guardian.py`): builds a quoted-phrase AND query (placeholders like "one's", "someone" are split out), then regex-matches the entry (first word inflectable, placeholders as wildcards) in article sentences to produce candidates for `llm.choose_quotes`.
- **PDF** (`pdf.py`): ReportLab with bundled DejaVu fonts (needed for IPA), built to `output/vocabulary.tmp` and then swapped into `output/vocabulary.pdf`.

## Cautions

- `data/vocab.db`, `data/remaining.txt` and `output/vocabulary.pdf` are tracked in git and hold the user's real progress. Do not delete or reset them when testing; use a copy.
- Each LLM or Guardian call costs API quota; detail generation makes several.
