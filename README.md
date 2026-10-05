# Word Bank

A personal vocabulary trainer for advanced learners of English, running in your
browser on your own computer.

## Contents

1. [What it does](#what-it-does)
2. [Quick start](#quick-start)
3. [Setting up the keys](#setting-up-the-keys)
4. [Using the app](#using-the-app)
5. [How it works](#how-it-works)
6. [Your data](#your-data)
7. [Troubleshooting](#troubleshooting)
8. [Problems found and how they were fixed](#problems-found-and-how-they-were-fixed)
9. [Known limitations and remaining challenges](#known-limitations-and-remaining-challenges)
10. [For developers](#for-developers)

## What it does

Word Bank draws from a fixed list of **5,000 entries**: 3,500 GRE-level words, and
1,500 phrases, idioms, allusions and foreign expressions used in English.

- **Every day** it picks five entries you have not mastered yet. For each it shows
  a pronunciation (a simple respelling and British IPA), an audio button, and the
  principal meaning.
- **Click an entry** to study it. You get every meaning, up to five example
  sentences (real quotes from **The Guardian** first, each linked to its article),
  and synonyms and antonyms.
- **Not quite right?** Type what should change, in plain English, and an AI
  language model revises the entry.
- **Accept** an entry once you are happy with it. It goes into your personal
  **PDF**, which has a linked contents page, and it is never picked again.

You can also look up any word or phrase yourself, browse earlier days, and search
everything you have accepted.

## Quick start

1. Install [uv](https://docs.astral.sh/uv/). It fetches the right Python and
   every library automatically.
2. Create a file named `.env` in this folder with your keys (see
   [Setting up the keys](#setting-up-the-keys)).
3. Start the app:
   - **Windows:** double-click `start.bat`.
   - **Mac or Linux:** run `./start.sh`.
   - **Any system:** run `uv run server.py` in this folder.
4. Your browser opens at <http://127.0.0.1:8000>. To stop the app, close the
   terminal window.

If a key is missing, the app does not start. It names what to add instead, for
example `Add these settings to the .env file, then start again: GROQ_API_KEY`.

## Setting up the keys

The app needs two services: an AI language model, through **Groq**, and **The
Guardian**'s article search. Both have free tiers. Put this in `.env`:

```
GROQ_API_KEY=...
GUARDIAN_API_KEY=...
LLM_MODEL=groq/openai/gpt-oss-120b
```

| Key | Where to get it |
|---|---|
| `GROQ_API_KEY` | Create a free account at <https://console.groq.com/keys> |
| `GUARDIAN_API_KEY` | Register for a free developer key at <https://open-platform.theguardian.com/access/> |
| `LLM_MODEL` | Leave it as shown. It names the model Groq runs |

**Using OpenAI instead of Groq:** set `LLM_MODEL=openai/<model-name>`, choosing
any OpenAI model that supports structured output, and add `OPENAI_API_KEY=...`.

`.env` holds your private keys. Anyone you give it to can use your accounts.

## Using the app

### A typical day

1. Open the app. **Today** shows five entries, picked the first time you open the
   app that day. Opening it again the same day shows the same page.
2. Click a card. The side panel loads its meanings, examples and synonyms. The
   first opening takes a few seconds while the content is fetched and written;
   after that it is instant.
3. Read it, and press the speaker button to hear it.
4. If something is off, type it in the box at the bottom and press **Edit**. For
   example: "drop the second quote", "the stress is on the last syllable", or
   "add the chemistry sense".
5. Press **Accept** when you are happy. The entry is final: it goes into the PDF
   and leaves the list for good.

### The screens

| Screen | What it shows | What you can do |
|---|---|---|
| **Today** | Today's cards. Phrases of more than two words show no respelling | **5 More Words** adds up to five entries and tells you when the list has run out. **Add** looks up any word or phrase you type |
| **Side panel** | Meanings, up to 5 examples (Guardian quotes first, then written examples labelled "Example sentence"), synonyms and antonyms | **Edit**, **Accept** and **Delete**. Guardian quotes are never reworded, only kept or dropped |
| **Browse** | A calendar. Highlighted days have accepted entries | Click a day to see what you accepted then. Past days are read-only and show only accepted entries |
| **All Words** | Every accepted entry, alphabetically, with its meaning and date | Search, open, or **Delete** |
| **PDF** | Your accepted entries: Words then Phrases, alphabetical, with a linked contents page | Opens in a new tab. Saved at `output/vocabulary.pdf` |

### Deleting

- **An entry on today's page:** it simply disappears.
- **An accepted entry:** it also leaves the PDF.
  - An entry from the 5,000 goes back into the list, so it can be picked again.
  - A word you typed yourself is not added to the list, but you can look it up
    again whenever you like.

### Keyboard

| Key | What it does |
|---|---|
| **Tab** | Moves between cards, the buttons and the list |
| **Enter** | Opens the card or row in focus |
| **Escape** | Closes the side panel and returns you to where you were |

While the side panel is open, Tab stays inside it.

## How it works

| Step | What happens | Service used |
|---|---|---|
| A card is created (daily pick, 5 More, Add) | The language model writes the pronunciation, respelling and principal meaning | Groq, one call per batch |
| An entry is opened for the first time | The language model writes the meanings and examples. The Guardian is searched; every sentence that really uses the entry is collected, and the model picks the best three | Groq, two calls; The Guardian, one call |
| You press Edit | The language model revises the entry from your instructions | Groq, one call |
| You press Accept or Delete | The PDF is rebuilt from scratch, then the change is saved | None |

Everything is stored on your computer. Only the words being looked up are sent to
Groq and The Guardian.

## Your data

| File | What it holds |
|---|---|
| `data/vocab.db` | Every day's entries, their content, and what you accepted |
| `data/remaining.txt` | The entries not yet accepted, which the daily pick draws from |
| `output/vocabulary.pdf` | Your PDF. It is rebuilt automatically, so it can always be recreated |
| `VOCABBASE.TXT` | The master list of 5,000 entries. It is never changed |

**Backing up:** copy `data/` somewhere safe from time to time. It holds all your
progress.

**Moving the app:** copy the whole folder, including `.env`, `data/` and
`output/`, to another place or computer that has uv. Then start it as usual.
Nothing is lost, and uv rebuilds its `.venv` folder if needed.

**About git:** the three progress files are tracked in this repository, which
makes git a backup. But it also means that checking out an older commit replaces
your progress with that commit's copy. Back up `data/` before doing that.

## Troubleshooting

Messages appear at the bottom of the page.

| Message | Meaning | What to do |
|---|---|---|
| *The LLM service failed. Try again in a minute.* | Groq was busy or limited the request, even after about 90 seconds of retrying | Wait a minute and try again |
| *The LLM provider rejected the API key in .env.* | `GROQ_API_KEY` is wrong or revoked | Fix the key in `.env` and restart the app |
| *The LLM provider does not know the model …* | `LLM_MODEL` has a typo or names a retired model | Set `LLM_MODEL=groq/openai/gpt-oss-120b` and restart |
| *The Guardian rejected GUARDIAN_API_KEY. Check it in .env.* | The Guardian key is wrong | Fix the key in `.env` and restart |
| *The Guardian's request limit has been reached. Try again later.* | The free Guardian key's daily or per-second limit is used up | Try again later, or tomorrow |
| *Could not reach The Guardian. Check the internet connection.* | There is no network | Reconnect, then open the entry again |
| *vocabulary.pdf is open in another program. Close it and try again.* | A PDF viewer such as Acrobat has the file locked, so it cannot be rebuilt. Nothing was changed | Close the PDF, then press Accept or Delete again |
| *Every entry in the vocabulary list is already on today's page or accepted.* | Nothing is left to pick | Look words up with Add instead |
| *That entry no longer exists. Reload the page.* | It was deleted, for example in another tab | Reload the page |
| *No accepted entries yet, so there is no PDF.* | Nothing has been accepted yet | Accept an entry first |

**A card or panel takes a long time:** the app is probably waiting out Groq's
per-minute limit. It retries for up to about 90 seconds before giving up, so let
it finish.

**The page did not load:** the "Try again" button reloads Today without
restarting the app.

## Problems found and how they were fixed

The app went through three code reviews and a full test with the real Groq and
Guardian services. These are the problems that could have affected you, and how
each is now handled.

| Problem | How it is handled now |
|---|---|
| Groq's free tier allows about **8,000 tokens a minute**, roughly five opened entries. Opening several in a row made the app give up after 14 seconds | The app keeps retrying for up to 90 seconds. Retries during a limit cost nothing, so you see a short pause instead of an error |
| A wrong Groq key was retried for over a minute, then reported as a service failure | Groq reports a bad key unusually. The app now recognises it, and tells you at once that the key was rejected |
| Accepting while the PDF was open in a viewer half-saved the entry | The PDF is rebuilt first. If the file is locked, nothing is saved, and you are told to close it |
| Two accepts at the same moment could leave one entry out of the PDF | Accepts and deletes now run one at a time |
| Entries with an apostrophe, such as "a baker's dozen" (182 of the 5,000), broke the PDF and could never be accepted | Fixed. All 5,000 entries have been test-built into a PDF |
| Double-clicking a card paid for its content two or three times | An entry's content is now fetched once, however many times it is opened |
| The same word could appear twice on a page ("Abase" and "abase"), or be accepted twice with different accents | Entries are compared ignoring case and accents |
| Guardian quotes sometimes included an author's note or letter footer ("Mum's the word! • Anthony Watt writes…") | Quotes are now cut at the Guardian's "•" separators and at numbered sentences |
| Quote search matched unrelated words ("abate" in "abattoir") and missed real forms ("decried" for "decry") | Matching now uses real English word endings |
| Keyboard users could Tab into the hidden side panel, or out of the open one | The panel behaves as a proper dialog |
| Pressing Enter twice in the Add box looked the word up twice | Enter is ignored while a lookup is running |

## Known limitations and remaining challenges

- **Speed of Accept and Delete grows with your collection.** Each one rebuilds
  the whole PDF: about 13 seconds at 1,500 accepted entries, and nearly a minute
  at 5,000. A second Accept waits for the first to finish.
- **Groq's free tier causes pauses.** Opening many new entries quickly can pause
  for up to a minute. A paid Groq tier, or a smaller model in `LLM_MODEL`, would
  avoid this.
- **The Guardian's free key has a daily limit.** Each newly opened entry uses
  one search.
- **Pronunciations come from the language model.** They are usually right but
  not always. One test gave an American rather than British pronunciation for
  "au contraire". Correct it with Edit, e.g. "use the British pronunciation".
- **Rare entries may have fewer than three Guardian quotes.** Written examples
  fill the gaps.
- **Quotes are only as good as their source.** The Guardian sometimes returns
  articles where the entry is a name (e.g. someone called Askew). The language
  model filters these out, and in testing it did so every time.
- **Audio uses your browser's built-in voice,** which reads foreign phrases as
  if they were English.
- **Single user, this computer only.** The app refuses requests from other
  websites and other machines. It is not designed to be shared over a network.
- **The language model can be wrong.** Treat definitions and written examples
  like a good dictionary draft, and use Edit when something looks off.

## For developers

```
uv run pytest                      # 91 tests; no API calls, real data untouched
uv run build_vocab.py              # check the vocabulary part files
uv run build_vocab.py --write      # rebuild VOCABBASE.TXT from parts/
```

| Path | Purpose |
|---|---|
| `server.py` | Web server, API routes and error messages |
| `config.py` | Settings from `.env`, checked at startup |
| `journal.py` | Rules for today, past days, revising, accepting and deleting |
| `db.py` | SQLite storage (`data/vocab.db`) |
| `vocab.py` | Master list and working list (`data/remaining.txt`) |
| `llm.py` | Language-model prompts via LiteLLM, with retries |
| `guardian.py` | Guardian search and sentence matching |
| `pdf.py` | PDF generation (ReportLab) |
| `static/` | The page: HTML, CSS, JavaScript |
| `tests/` | Automated tests |
| `parts/`, `build_vocab.py` | Sources for rebuilding `VOCABBASE.TXT` |
| `fonts/` | DejaVu fonts for IPA in the PDF (free licence in `fonts/LICENSE`) |
| `CLAUDE.md` | Architecture notes for working on the code |
| `DEBUG.md` | The latest debugging and test report |

`DAILY_COUNT` (entries per day, 5) and `MAX_EXAMPLES` (examples per entry, 5) are
constants in `journal.py`.
