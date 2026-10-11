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
8. [Limitations: what, why, and possible solutions](#limitations-what-why-and-possible-solutions)
9. [Problems found and how they were fixed](#problems-found-and-how-they-were-fixed)
10. [For developers](#for-developers)

## What it does

Word Bank draws from a fixed list of **5,000 entries**: 3,500 GRE-level words, and
1,500 phrases, idioms, allusions and foreign expressions used in English.

- **Every day** it picks five entries you have not mastered yet. For each it shows
  a pronunciation (a simple respelling and British IPA, from Wiktionary where it
  has one), an audio button, and the principal meaning.
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

If a key is missing or blank, the app does not start. It names what to add
instead, for example `Add these settings to the .env file, then start again:
OPENAI_API_KEY`.

## Setting up the keys

The app uses three services:

- **Groq**, the main AI language model. It is free.
- **OpenAI**, the standby model, used only when Groq cannot answer. It is paid
  per use.
- **The Guardian**'s article search. It is free.

Put this in `.env`:

```
GROQ_API_KEY=...
OPENAI_API_KEY=...
GUARDIAN_API_KEY=...
LLM_MODEL=groq/openai/gpt-oss-120b
```

| Key | Where to get it |
|---|---|
| `GROQ_API_KEY` | Create a free account at <https://console.groq.com/keys> |
| `OPENAI_API_KEY` | Create a key at <https://platform.openai.com/api-keys> and add a little credit |
| `GUARDIAN_API_KEY` | Register for a free developer key at <https://open-platform.theguardian.com/access/> |
| `LLM_MODEL` | Leave it as shown. It names the model Groq runs |
| `LLM_FALLBACK_MODEL` | Optional. The standby model; `openai/gpt-4o-mini` if not set |

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
| **Side panel** | Meanings, up to 5 examples (Guardian quotes first, then written examples labelled "Example sentence"), synonyms and antonyms | **Edit**, **Accept** and **Delete**. While one of them runs, the others wait. Guardian quotes are never reworded, and are removed only when you ask |
| **Browse** | A calendar. Highlighted days have accepted entries | Click a day to see what you accepted then. Past days are read-only and show only accepted entries |
| **All Words** | Every accepted entry, alphabetically, with its meaning and date | Search (ignoring accents), open, or **Delete** |
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

| Step | What happens | Services used |
|---|---|---|
| A card is created (daily pick, 5 More, Add) | The entry's British pronunciation and senses are looked up in a local copy of Wiktionary. The language model writes the principal meaning from those senses and the respelling. The pronunciation is Wiktionary's, copied exactly, when it has one | One AI call per batch |
| An entry is opened for the first time | The language model writes the meanings, based on Wiktionary's senses, and examples. The Guardian is searched; every sentence that really uses the entry is collected, and the model picks the best three | Two AI calls; one Guardian search |
| You press Edit | The language model revises the entry from your instructions | One AI call |
| You press Accept or Delete | The PDF is rebuilt from scratch, then the change is saved | None |

### Which AI model answers

Every AI call goes to **Groq first**. If Groq cannot answer, the same call goes
**straight to OpenAI** (gpt-4o-mini), with no waiting. This covers its per-minute
limit, its daily allowance, an outage, no reply within 30 seconds, or a
malformed answer. So:

- **When Groq is fine,** you pay nothing.
- **When Groq refuses,** you wait about half a second longer than usual.
- **If Groq hangs,** you wait at most 30 seconds longer.
- **You never get an error because of Groq's limits.** You see one only if
  OpenAI fails too, or a key or model name is wrong.

Each switch is written in the terminal window as one line, with Groq's reason.

### Where pronunciations and meanings come from

`dictionary.json` holds Wiktionary's British pronunciation (IPA) and senses for
4,426 of the 5,000 entries; 2,384 of them have a British pronunciation. It is
built once from the free [kaikki.org](https://kaikki.org) extract of Wiktionary
and is part of the app, so lookups need no network.

- **A word with two pronunciations** ("buffet": a meal, or to strike) is shown
  with the pronunciation that belongs to the meaning on the card.
- **A variant spelling** ("gibe") uses its main spellings' entries ("jibe",
  "gybe").
- **An entry Wiktionary lacks, or one without a British pronunciation,** gets
  the language model's pronunciation, as before.
- **Edit keeps the pronunciation** unless your instructions ask to change it.

Everything is stored on your computer. Only the words being looked up are sent to
Groq, OpenAI and The Guardian.

## Your data

| File | What it holds |
|---|---|
| `data/vocab.db` | Every day's entries, their content, and what you accepted |
| `data/remaining.txt` | The entries not yet accepted, which the daily pick draws from |
| `output/vocabulary.pdf` | Your PDF. It is rebuilt automatically, so it can always be recreated |
| `VOCABBASE.TXT` | The master list of 5,000 entries. It is never changed |
| `dictionary.json` | Wiktionary's pronunciations and senses for the master list. It changes only when rebuilt |

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
| *Both LLM services failed. Try again in a minute.* | Groq could not answer, and OpenAI failed too, three times | Try again in a minute. If it persists, check the internet connection and your OpenAI credit |
| *The groq provider rejected its API key in .env.* | `GROQ_API_KEY` is wrong or revoked | Fix the key in `.env` and restart the app |
| *The openai provider rejected its API key in .env.* | `OPENAI_API_KEY` is wrong or revoked. You see this only when Groq could not answer and OpenAI was needed | Fix the key in `.env` and restart |
| *The … provider does not know the model …* | `LLM_MODEL` or `LLM_FALLBACK_MODEL` has a typo or names a retired model | Correct it in `.env` and restart |
| *The Guardian rejected GUARDIAN_API_KEY. Check it in .env.* | The Guardian key is wrong | Fix the key in `.env` and restart |
| *The Guardian's request limit has been reached. Try again later.* | The free Guardian key's daily or per-second limit is used up | Try again later, or tomorrow |
| *Could not reach The Guardian. Check the internet connection.* | There is no network | Reconnect, then open the entry again |
| *vocabulary.pdf is open in another program. Close it and try again.* | A PDF viewer such as Acrobat has the file locked, so it cannot be rebuilt. Nothing was changed | Close the PDF, then press Accept or Delete again |
| *Every entry in the vocabulary list is already on today's page or accepted.* | Nothing is left to pick | Look words up with Add instead |
| *That entry no longer exists. Reload the page.* | It was deleted, for example in another tab | Reload the page |
| *"…" is already accepted.* | It was accepted, for example in another tab, while an Edit was running. The edit was not saved | Nothing; the accepted version is the one in the PDF |
| *No accepted entries yet, so there is no PDF.* | Nothing has been accepted yet | Accept an entry first |

**A panel takes 30 seconds or more:** Groq accepted the request but did not
answer, so the app waited out its 30-second limit before asking OpenAI. The
terminal shows a line ending in `Timeout`.

**The page did not load:** the "Try again" button reloads Today without
restarting the app.

## Limitations: what, why, and possible solutions

### The language model

**About half the entries still get the model's pronunciation, which is
sometimes wrong.**
- *Why:* Wiktionary has a British pronunciation for 2,384 of the 5,000 entries
  (2,144 of the 3,500 words, but only 242 of the 1,500 phrases). For the rest,
  and for words you type that are not in the list, the model writes the IPA from
  patterns it has learned. Foreign phrases and stress are its weak spots.
  Pronunciations Wiktionary marks only as American, or not marked at all, are
  not used, because they are often American.
- *Solutions:* use Edit ("the stress is on the second syllable"). A second
  dictionary source with British IPA for phrases would close more of the gap.

**The respelling ("ab-JEKT") is still written by the model.**
- *Why:* Wiktionary has no respellings. Given the IPA, Groq got the format wrong
  (stress in the wrong syllable, or capitals missing) on 4 or 5 of 40 cards in
  testing, against 2 in 40 before it was given the IPA, so it did not help on
  Groq. OpenAI got 0 or 1 of 40 wrong.
- *Solutions:* Edit; or generate the respelling from the IPA in code, with a
  table of sounds.

**Definitions and written examples can still be wrong.**
- *Why:* the model writes them in its own words. They are now based on
  Wiktionary's senses where it has the entry, but the model chooses among those
  senses, and occasionally leans on the one Wiktionary lists first rather than
  the commonest (for "terra firma" it led with the legal sense). In a side-by-side
  check of 30 entries, 26 meanings were about as good as before, 1 better and 3
  worse or debatable.
- *Solutions:* treat them as a good dictionary draft and use Edit. Guardian
  quotes are real text, which is why they come first.

**Wiktionary is edited by volunteers.**
- *Why:* it is good, but not perfect. Some common words lack a British
  pronunciation ("genesis"), and senses include rare and technical ones.
- *Solutions:* the model fills gaps and is told to prefer senses in current
  general use. Rebuilding `dictionary.json` picks up later corrections.

**Cards cost more tokens.**
- *Why:* each card request now carries Wiktionary's senses: a typical batch of
  five grew from about 350 to 750 tokens, so Groq's free tier is used up a
  little sooner.
- *Solutions:* send fewer senses per entry (`MAX_SENSES` in
  `build_dictionary.py`).

**Entries written on the same day may come from two different models.**
- *Why:* when Groq cannot answer, OpenAI writes that part. The two write in
  slightly different styles. Quality was similar in testing.
- *Solutions:* to use one model only, set `LLM_MODEL=openai/gpt-4o-mini` (always
  paid), or take a paid Groq tier, which has higher limits.

**Removing a Guardian quote with Edit relies on the model's judgement.**
- *Why:* the model is first asked whether your instructions ask to remove a
  quote, and a quote is removed only if it says yes. In testing that was right
  every time: 0 of 33 unrelated edits lost a quote, and 12 of 12 removal
  requests were followed exactly. That testing was on OpenAI, though; the check
  could not be measured on Groq, whose daily allowance had run out.
- *Solutions:* a "remove" button next to each quote would take the model out of
  this decision entirely.

### Cost and limits of the services

**Heavy use costs a little money.**
- *Why:* Groq's free tier allows about 8,000 tokens a minute (roughly five newly
  opened entries) and 200,000 a day (roughly 130). Beyond that, OpenAI answers,
  and it is paid per use. At gpt-4o-mini's prices that is a small fraction of a
  cent per entry; check OpenAI's pricing page for current rates. Normal use (five
  entries a day) stays within Groq's free tier.
- *Solutions:* a paid Groq tier, or a spending limit on the OpenAI account.

**A wrong OpenAI key is noticed only when OpenAI is first needed.**
- *Why:* at startup the app checks that each key is present, but it cannot tell
  whether a key works without spending a request. A bad OpenAI key therefore
  shows up only on a day Groq falls back.
- *Solutions:* a test request to both services at startup. It would cost
  almost nothing, but the app would then need the network before it could
  start.

**A new entry cannot be opened while The Guardian is unavailable.**
- *Why:* an entry's content is generated in one step, including the quote
  search. If The Guardian is down, or its free key's daily limit is used up, the
  whole step fails and nothing is stored. There is no standby service for
  quotes.
- *Solutions:* save the entry without quotes and add them later, or use a paid
  Guardian key. Entries opened before are not affected.

**Rare entries may have fewer than three Guardian quotes, and a quote's article
can be off-topic.**
- *Why:* The Guardian may simply not use the entry often, and its search
  sometimes returns articles where the entry is a name ("Kathleen Askew"). The
  model filters those out, and did so every time in testing.
- *Solutions:* written examples fill the gaps; Edit can remove a weak quote.

### Speed

**Accept and Delete slow down as the collection grows.**
- *Why:* each rebuilds the whole PDF (two passes, for the contents page): about
  13 seconds at 1,500 accepted entries, and nearly a minute at 5,000. They run
  one at a time, so a second Accept waits for the first.
- *Solutions:* build the PDF in the background, or in sections that are only
  rebuilt when they change.

**One AI call can take up to about 30 seconds longer than usual.**
- *Why:* if Groq accepts a request but never answers, the app waits 30 seconds
  (its limit) before asking OpenAI. Groq normally answers in under 10 seconds,
  and a refusal comes back in about half a second.
- *Solutions:* a shorter limit would switch sooner, but would also abandon slow
  answers from Groq that would have arrived.

### Audio, scope and data

**Audio reads foreign phrases as if they were English.**
- *Why:* it uses your browser's built-in British voice.
- *Solutions:* choose a voice per language, or use a text-to-speech service.

**Single user, this computer only.**
- *Why:* the app refuses requests from other websites and other machines, to
  keep your keys and data private. It has no accounts.
- *Solutions:* sharing would need accounts, a proper database server, and
  hosting.

**Checking out an older git commit replaces your progress.**
- *Why:* your progress files are tracked in git, which is what makes git a
  backup.
- *Solutions:* back up `data/` first, or move the progress files out of git.

## Problems found and how they were fixed

The app went through five code reviews, and full tests with the real Groq, OpenAI
and Guardian services.

| Problem | How it is handled now |
|---|---|
| Pronunciations came only from the model, which got some wrong ("unfathomable", "gibe", "entourage", "adept" as a noun) | Taken from Wiktionary where it has a British one: 2,384 entries |
| **Edit sometimes rewrote the pronunciation you had not asked about** | It is kept unless your instructions ask to change it |
| With Wiktionary's senses listed, OpenAI sometimes returned one card per sense, so cards got the wrong meanings | Each card names its entry, and a reply that does not match the entries is rejected and asked again |
| Groq's free-tier limits made the app wait for up to 90 seconds, then sometimes fail; when its daily allowance ran out, nothing worked | Groq is never waited for. If it refuses, OpenAI answers straight away. In testing, 36 refusals during a full test caused no errors, and the slowest panel took 6 seconds instead of 81 |
| A wrong Groq key was retried for over a minute, then reported as a service failure | Recognised at once, and reported as a rejected key |
| **Edit sometimes deleted Guardian quotes you had not asked about** (about one edit in four, on both Groq and OpenAI) | Quotes are removed only when your instructions ask for it |
| Pressing Accept while an Edit was still running saved the edit but left the old version in the PDF | Edit, Accept and Delete lock each other, and the server checks again before saving an edit |
| Accepting while the PDF was open in a viewer half-saved the entry | The PDF is rebuilt first. If it is locked, nothing is saved |
| Two accepts at the same moment could leave one entry out of the PDF | Accepts and deletes run one at a time |
| Entries with an apostrophe, such as "a baker's dozen" (182 of the 5,000), broke the PDF | Fixed. All 5,000 entries have been test-built into a PDF |
| Double-clicking a card paid for its content two or three times | Content is fetched once, however many times the entry is opened |
| The same word could appear twice ("Abase" and "abase"), or be accepted twice with different accents | Entries are compared ignoring case and accents |
| Guardian quotes included author notes or letter footers, or lost their closing quote mark | Quotes are cut at the Guardian's "•" separators and keep their quote marks; every stored quote was checked word for word against its article |
| Quote search matched unrelated words ("abate" in "abattoir") and missed real forms ("decried") | Matching uses real English word endings |
| A blank key in `.env` let the app start | It is named at startup, like a missing key |
| Keyboard users could Tab into the hidden side panel; Enter twice looked a word up twice | The panel behaves as a proper dialog; Enter is ignored while a lookup runs |
| Search missed accented entries; long words on accepted cards broke mid-word | Search ignores accents; the badge sits above the word |

## For developers

```
uv run pytest                      # 127 tests; no API calls, real data untouched
uv run build_vocab.py              # check the vocabulary part files
uv run build_vocab.py --write      # rebuild VOCABBASE.TXT from parts/
uv run build_dictionary.py         # rebuild dictionary.json from Wiktionary
```

`build_dictionary.py` downloads the 523 MB kaikki.org extract to `downloads/`
(not in git) the first time, then takes about two minutes. Rebuild it after
changing `VOCABBASE.TXT`. Wiktionary's content is under CC BY-SA; the PDF's title
page credits it.

| Path | Purpose |
|---|---|
| `server.py` | Web server, API routes and error messages |
| `config.py` | Settings from `.env`, checked at startup |
| `journal.py` | Rules for today, past days, revising, accepting and deleting |
| `db.py` | SQLite storage (`data/vocab.db`) |
| `vocab.py` | Master list and working list (`data/remaining.txt`) |
| `llm.py` | Language-model prompts via LiteLLM: Groq first, OpenAI on failure |
| `guardian.py` | Guardian search and sentence matching |
| `dictionary.py`, `build_dictionary.py` | Wiktionary lookup, and the script that builds `dictionary.json` |
| `pdf.py` | PDF generation (ReportLab) |
| `static/` | The page: HTML, CSS, JavaScript |
| `tests/` | Automated tests |
| `parts/`, `build_vocab.py` | Sources for rebuilding `VOCABBASE.TXT` |
| `fonts/` | DejaVu fonts for IPA in the PDF (free licence in `fonts/LICENSE`) |
| `CLAUDE.md` | Architecture notes for working on the code |
| `DEBUG.md` | The latest debugging and test report, with the technical limitations |

`DAILY_COUNT` (entries per day, 5) and `MAX_EXAMPLES` (examples per entry, 5) are
constants in `journal.py`.
