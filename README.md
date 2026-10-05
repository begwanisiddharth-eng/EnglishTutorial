# Word Hoard

A local, in-browser app for advanced learners of English. Each day it shows five
entries picked at random from 5,000 (3,500 GRE-level words and 1,500 phrases,
idioms, allusions and foreign expressions). Click an entry to study its meanings,
real example sentences from The Guardian, synonyms and antonyms. Refine the entry
with feedback, then accept it into a PDF with a table of contents.

## Requirements

- [uv](https://docs.astral.sh/uv/) (it installs the right Python and all libraries itself)
- An internet connection
- API keys in a `.env` file in this folder:

```
GROQ_API_KEY=...
GUARDIAN_API_KEY=...
LLM_MODEL=groq/openai/gpt-oss-120b
```

Get a free Guardian key at https://open-platform.theguardian.com/access/.
To use OpenAI instead of Groq, set `LLM_MODEL=openai/<model-name>` (any OpenAI
model that supports structured output) and add `OPENAI_API_KEY=...`.

## Run

Double-click `start.bat` (Windows) or run `./start.sh` (Mac/Linux). Or, from this folder:

    uv run server.py

The browser opens at http://127.0.0.1:8000. Close the terminal window to stop.

## Using it

- **Today**: five entries, each with a pronunciation respelling, an audio button
  and its principal meaning. Phrases of more than two words show no respelling.
  Add five more entries, or look up any word or phrase.
- **Side panel** (click a card): all meanings, up to 5 examples (Guardian quotes
  first, linked to the article; written examples labelled "Example sentence"),
  synonyms and antonyms.
  - **Edit**: type what should change (e.g. "drop the second quote", "the
    stress is on the last syllable") and the LLM revises the entry. Guardian
    quotes are never reworded, only kept or dropped.
  - **Accept**: the entry is final. It goes into the PDF and leaves the
    vocabulary list for good. Edit and Accept are then greyed out.
  - **Delete**: removes the entry. If it was accepted, it also leaves the PDF and
    returns to the vocabulary list.
- **Browse**: a calendar of past days. A past day is read-only and shows only the
  entries accepted that day; days with none are not shown.
- **All Words**: every accepted entry, alphabetically, with Delete.
- **PDF**: accepted entries, Words then Phrases, alphabetical, with a linked
  contents page. Saved at `output/vocabulary.pdf`.

## Moving the app

Copy the whole folder, including `.env`, `data/` and `output/`, to another
location or computer with uv installed, then run it as above. Nothing is lost.
uv rebuilds the `.venv` folder automatically if it no longer works after the move.
Anyone you give the folder to can use your API keys.

## Files

| Path | Purpose |
|---|---|
| `server.py` | Web server and API routes |
| `config.py` | Settings from `.env`, checked at startup |
| `journal.py` | Rules for today, past days, revising, accepting and deleting |
| `db.py` | SQLite storage (`data/vocab.db`) |
| `vocab.py` | Working copy of the vocabulary list (`data/remaining.txt`) |
| `llm.py` | LLM prompts via LiteLLM, retried with tenacity |
| `guardian.py` | Guardian search and sentence matching |
| `pdf.py` | PDF generation (ReportLab) |
| `static/` | The page: HTML, CSS, JavaScript |
| `VOCABBASE.TXT` | Master list of 5,000 entries (never modified) |
| `parts/`, `build_vocab.py` | Sources for rebuilding `VOCABBASE.TXT` |
| `fonts/` | DejaVu fonts for IPA in the PDF (free licence in `fonts/LICENSE`) |
| `tests/` | Tests: `uv run pytest` (no API calls, real data untouched) |

## Known limitations

- Pronunciations come from the LLM and are sometimes wrong. Correct them with Edit.
- Rare entries may have fewer than three usable Guardian quotes. Written examples fill the gaps.
- Accept and Delete are refused while `vocabulary.pdf` is open in a viewer that locks it (e.g. Acrobat). Close it and try again.
- The audio button uses the browser's built-in voice, which reads foreign phrases as if they were English.
