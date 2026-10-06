# Review: fourth round, end to end

Word Bank at `2debb04`, 5 October 2026. A full end-to-end test with real Groq,
OpenAI and Guardian calls, a browser pass, and a reading of every source file for
simplification. **Every finding below has been fixed.** DEBUG.md has the evidence
and the retest.

## Findings

| # | Severity | Finding | Fix |
|---|---|---|---|
| H1 | High | Edit silently deleted Guardian quotes it was not asked to touch | Drops count only when the model first says the feedback asked for one |
| H2 | High | Accept or Delete during an Edit: the PDF and the database disagreed | The revision is checked again and written under `COLLECTION_LOCK`; the page locks the drawer footer |
| M1 | Medium | The closing quote mark of a Guardian quote was cut off | The closing mark goes into the sentence splitter's lookbehind |
| M2 | Medium | Groq's daily token limit: 74–90 s of useless retries, then "Try again in a minute" | Not retried; its own message. Since superseded: any Groq refusal now switches to OpenAI at once (see DEBUG.md) |
| L1 | Low | An empty `GROQ_API_KEY=` passed the startup check | Blank `.env` values count as unset |
| L2 | Low | All Words search was not accent-insensitive | A JavaScript `fold`, matching `vocab.fold` |
| L3 | Low | Card titles next to the "accepted" badge broke mid-word | Title starts below the badge and has the full width |

### H1. Edit deleted Guardian quotes

**Evidence.** The test feedback had nothing to do with examples ("Shorten the
principal meaning…", "Add one more synonym."). Even so, revisions removed
Guardian quotes. Zugzwang and dulcet each lost all three. A lost quote cannot
come back, because Edit never adds Guardian quotes.

**Root cause.** The model decided which quotes survived, and it does so
loosely. Every scheme was tried on both models, with the same entries and
feedback:

| Scheme | Unrelated revisions that lost a quote |
|---|---|
| `keep_quotes` (the original: a quote is kept only if listed) | Groq 7 of 24; gpt-4o-mini 3 of 12 |
| `drop_quotes` (a quote is removed only if listed) | gpt-4o-mini 4 of 33 |
| `drop_quotes` gated by `feedback_asks_to_remove_quotes` (the fix) | gpt-4o-mini **0 of 33**; genuine requests to remove: **12 of 12 exact** |

So the model is not the cause: both models drop quotes unasked. Switching to
gpt-4o-mini alone would not have fixed it.

**Fix.** `llm.Revision` now has a yes/no field, `feedback_asks_to_remove_quotes`,
before `drop_quotes`, so the model decides it first. `llm.revise` ignores
`drop_quotes` unless that field is true, and range-checks only the drops it
applies.

**Not measured:** the gated scheme on Groq. Groq's daily allowance was used up
when the comparison was run.

### H2. Accept or Delete while an Edit was running

**Evidence.** A revision was in flight, and an Accept arrived 0.3 s later. The
entry was stored as accepted with the revised content, while the PDF kept the
old content. A Delete during an Edit returned `200` with a `null` body. In the
page, Accept and Delete stayed enabled while Edit ran.

**Root cause.** `journal.revise` checked `editable()` before the LLM call (which
takes seconds), and then wrote without checking again.

**Fix.**
- `journal.revise` keeps the LLM call outside the lock, then checks the entry
  again under `COLLECTION_LOCK` and writes there. An accept or delete made in
  the meantime wins, and the edit gets "… is already accepted" or "That entry
  no longer exists".
- In the page, `drawerAction` disables feedback, Edit, Accept and Delete while
  any of them runs. `setFooter` now reads "loaded" from `entry.detail`, so its
  `loaded` argument is gone.

### M1. Closing quote marks cut off

**Root cause.** The optional closing mark in `SENTENCE_END` was part of the
separator, which `re.split` discards:
`'“… a crime.” The book…'` split as `'“… a crime.'`.

**Fix.** `(?:(?<=[.!?])|(?<=[.!?]["”’]))\s+(?=…)`: the closing mark is now only
looked behind, so it stays with its sentence.

One quote, from an "incubus" article, still opens with `“` and has no closing
mark. That is correct: the quotation runs on into the next sentence in the
article.

### M2. Groq's daily token limit

**Root cause.** Groq sends the daily limit as the same 429 and `"type":"tokens"`
as the per-minute limit. Only the message differs: "tokens per day (TPD): Limit
200000".

**Fix.**
- `llm.daily_limit_reached` checks the message text. `worth_retrying` does not
  retry it.
- `server.llm_failed` answers "Groq's daily token allowance is used up. It
  refills gradually; try again later."
- The test fixture uses Groq's exact message, so a change in Groq's wording
  would show up in the tests.

### L1–L3

- **L1.** `config.load_env_file` removes variables whose value in `.env` is blank,
  so `validate_environment` names them.
- **L2.** `fold()` in `static/app.js`: lowercase, œ/æ, NFKD, then marks
  removed.
- **L3.** The root cause was not the wrapping rule. A `<button>` sizes itself to
  its longest word, and here that word plus the 4rem kept clear for the badge
  was wider than the card. The old `word-break: break-word` hid this by breaking
  mid-word; a plain `overflow-wrap: break-word` let the button grow wider than
  the card and run under the badge. `hyphens: auto` was tried, but Chromium
  produced no hyphen, so it was dropped. Now the title sits below the badge
  (`margin-top: 1.1rem`) with the full width, and `overflow-wrap: anywhere`
  keeps any extreme word inside the card.

## Simplification

The code was already lean; no dead code was found.

| # | Done | Change |
|---|---|---|
| S1 | Yes | Quote removal is opt-in and gated (H1); same size as before |
| S2 | Yes | Every write to the collection goes through `COLLECTION_LOCK` (H2) |
| S3 | Yes | `drawerAction` replaces the `setFooter` calls after each drawer action; `setFooter` lost its `loaded` argument |
| S4 | Yes | `db.card_json` replaces the duplicated card encoding in `insert_cards` and `update_card` |
| S5 | Yes | One `fold()` for the page search (L2) |

Considered and rejected:

- **A names-only query for `refuse_if_accepted`.** At 5,000 accepted entries
  it would save about 110 ms (125 ms against 14 ms), next to a 55 s PDF
  rebuild.
- **Merging the two Guardian error handlers.** They give different messages.
- **Pruning `DETAIL_LOCKS`.** It holds one small lock per opened entry, so it
  is not a leak.

## Remaining (not code defects)

- **The language model's pronunciations,** on both models. "raison d'état" was
  wrong on both; Groq also got the stress of "unfathomable" wrong. There were
  occasional American spellings ("savory", "cozy"). These are documented in
  the README.
- **The gated quote rule on Groq** is unmeasured (see H1).
