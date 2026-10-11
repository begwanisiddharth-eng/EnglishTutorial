"""LLM calls through LiteLLM: the primary model first, the fallback at once if it fails; retried with tenacity."""
import json
import logging

import litellm
from litellm import completion
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

import config
import dictionary
import vocab

log = logging.getLogger(__name__)
litellm.suppress_debug_info = True  # its "Give Feedback / Get Help" banner on every failed call

# Groq is never waited for: any refusal or failure (rate limit, daily allowance, outage, timeout,
# malformed reply) switches to the fallback at once. Groq normally answers within 10 s.
PRIMARY_TIMEOUT_SECONDS = 30
FALLBACK_TIMEOUT_SECONDS = 60
# Retries now cover only malformed replies and a failing fallback, so a few quick ones suffice.
MAX_ATTEMPTS = 3
# A rejected key (401, 403) or unknown model (404) is a setup mistake: reported, never retried or
# hidden by the fallback. Judged by status, not exception type: litellm reports Groq's "Invalid API
# Key" as a BadRequestError with status 401.
PERMANENT_STATUS = {401, 403, 404}


def permanent(error):
    """Return True for errors that retrying or switching cannot fix: setup mistakes and interrupts."""
    return not isinstance(error, Exception) or getattr(error, "status_code", None) in PERMANENT_STATUS


retrying = retry(stop=stop_after_attempt(MAX_ATTEMPTS), wait=wait_exponential(min=1, max=4), reraise=True,
                 retry=retry_if_exception(lambda error: not permanent(error)))

CARD_PROMPT = """You are a lexicographer writing for advanced learners of English.
For each entry below (a word, phrase, idiom, allusion, or foreign expression
used in English), give:
- entry: the entry exactly as written after its number.
- meaning: a definition of its principal meaning, at most 20 words. Write a
  definition, never an example sentence.
- group: 0, unless numbered pronunciations are listed under the entry: then the
  number of the one whose senses include that meaning, or 0 if none does. Those
  senses are there only for this choice; do not base the meaning on them.
- pronunciation: if a pronunciation is listed for the entry, or for the group
  you chose, copy it exactly. Otherwise, the British English (Received
  Pronunciation) IPA transcription
  as given by the Oxford or Cambridge dictionaries, between slashes, with
  correct primary and secondary stress marks. For foreign expressions, give the
  pronunciation British English speakers use.
- respelling: the same pronunciation as a simple respelling for readers who do
  not know IPA. Syllables joined by hyphens, only the syllable with primary
  stress (after ˈ) in capitals, words separated by spaces. Use sh as in shoe, ch as in church, zh as in
  measure, th as in thin. Examples: manumit -> man-yoo-MIT,
  volatile -> VOL-uh-tyle, faute de mieux -> foht duh MYUR.

Use British spelling. Return exactly one card per numbered entry, in the same
order, even when an entry lists several pronunciations.

Entries:
{entries}"""


DETAIL_PROMPT = """You are a lexicographer writing for advanced learners of English.
For the entry "{entry}" give:
- senses: every distinct meaning in current use, most common first. For each,
  the part of speech (for multi-word entries: idiom, phrase, or expression) and
  a clear definition of at most 25 words.
- examples: up to 5 natural example sentences in British English showing the
  entry in use, covering different senses where possible. Each sentence must
  contain the entry or an inflected form of it.
- synonyms: 3 to 5 near-synonyms (words or short phrases), most common first.
- antonyms: 2 to 4 antonyms, or none if the entry has no real opposite.
Use British spelling throughout."""


CHOOSE_PROMPT = """Below are sentences from The Guardian containing the English entry
"{entry}" (principal meaning: {meaning}).
Choose up to 3 that best show an advanced learner how the entry is used:
- the entry must be used in its ordinary sense, not as a name, brand or title;
- the sentence must make sense on its own, without the rest of the article;
- prefer variety of context.
Return the numbers of the chosen sentences, best first. Return an empty list if
none qualify.

{listing}"""


REVISE_PROMPT = """You are a lexicographer revising a dictionary entry for advanced
learners of English. Use British spelling and British (Received Pronunciation) IPA.

Entry: "{entry}"
Current content (JSON):
{current}

The Guardian quotes are real published sentences: never reword them. First set
feedback_asks_to_remove_quotes: true only if the feedback explicitly asks to remove
one or more Guardian quotes. Only then list their numbers in drop_quotes; otherwise
leave it empty. Likewise set feedback_asks_to_change_pronunciation: true only if the
feedback asks to change the pronunciation or the respelling.

Learner's feedback:
{feedback}

Apply the feedback and return the complete revised entry. Change only what the
feedback asks for and keep everything else exactly as it is. Written examples must
contain the entry. Kept quotes plus written examples must total at most {max_examples}."""


class Choice(BaseModel):
    """Numbers of the chosen sentences."""
    chosen: list[int] = Field(max_length=3)


class Sense(BaseModel):
    """One meaning of an entry."""
    part_of_speech: str
    definition: str


class Detail(BaseModel):
    """All meanings of an entry with example sentences."""
    senses: list[Sense]
    examples: list[str] = Field(max_length=5)
    synonyms: list[str]
    antonyms: list[str]


class Revision(BaseModel):
    """A complete revised entry; Guardian quotes are referenced by number only.

    Models dropped quotes unasked: about a quarter of the time when quotes had to be listed to
    be kept, and still one time in eight when listed to be dropped. So a drop counts only when
    the model first says the feedback asked for it; the flag comes first so it is decided first.
    Models also replaced Wiktionary's pronunciation unasked, so the pronunciation is gated the same way.
    """
    feedback_asks_to_remove_quotes: bool
    drop_quotes: list[int]
    feedback_asks_to_change_pronunciation: bool
    pronunciation: str
    respelling: str
    meaning: str
    senses: list[Sense]
    written_examples: list[str]
    synonyms: list[str]
    antonyms: list[str]


class Card(BaseModel):
    """Pronunciation and principal meaning of one entry."""
    pronunciation: str
    respelling: str
    meaning: str


class Summary(BaseModel):
    """A card as the model writes it: the entry, its meaning, then the pronunciation group it comes from.

    The entry is repeated so that cards can be matched to entries: gpt-4o-mini sometimes made one
    card per listed group, and a count alone would not catch cards in the wrong order.
    """
    entry: str
    meaning: str
    group: int
    pronunciation: str
    respelling: str


class CardBatch(BaseModel):
    """Cards for a list of entries, in order."""
    cards: list[Summary]


def ask_model(model, timeout, prompt, schema, valid):
    """Send one prompt to one model; return the reply parsed into schema, raising ValueError if not valid.

    max_retries=0 because the OpenAI SDK would otherwise retry on its own, waiting as it likes.
    """
    response = completion(model=model, messages=[{"role": "user", "content": prompt}],
                          response_format=schema, timeout=timeout, max_retries=0)
    reply = schema.model_validate_json(response.choices[0].message.content)
    if not valid(reply):
        raise ValueError(f"reply does not fit the request: {reply}")
    return reply


def ask(prompt, schema, valid=lambda reply: True):
    """Ask the primary model, switching to the fallback at once if it refuses, fails or replies wrongly."""
    try:
        return ask_model(config.LLM_MODEL, PRIMARY_TIMEOUT_SECONDS, prompt, schema, valid)
    except Exception as error:
        if permanent(error):
            raise
        log.warning("%s failed for %s, using %s. %s: %s", config.LLM_MODEL, schema.__name__,
                    config.LLM_FALLBACK_MODEL, type(error).__name__, error)
        return ask_model(config.LLM_FALLBACK_MODEL, FALLBACK_TIMEOUT_SECONDS, prompt, schema, valid)


def shows_pronunciation(entry):
    """Return True for entries short enough (one or two words) to show a pronunciation."""
    return len(entry.split()) <= 2


def make_card(entry, card):
    """Combine an entry with its card fields, dropping pronunciation for longer phrases."""
    fields = card.model_dump()
    if not shows_pronunciation(entry):
        fields.update(pronunciation="", respelling="")
    return {"entry": entry, **fields}


def pronunciation_listing(groups):
    """Return an entry's Wiktionary pronunciations as indented lines for the card prompt."""
    if len(groups) == 1:
        return f"   pronunciation: {groups[0]['ipa']}"
    lines = []
    for n, group in enumerate(groups, 1):
        said = group["ipa"] or "not listed"
        lines += [f"   pronunciation {n}: {said}, for these senses:"] + [f"     {s}" for s in group["senses"]]
    return "\n".join(lines or ["   (no pronunciation listed)"])


def listed_pronunciation(summary, groups):
    """Return Wiktionary's pronunciation for the card: the only one, or the chosen group's, or ""."""
    if len(groups) == 1:
        return groups[0]["ipa"]
    return groups[summary.group - 1]["ipa"] if summary.group else ""


def summary_card(entry, summary, groups):
    """Make the card, taking the pronunciation from Wiktionary when it has one for the meaning."""
    pronunciation = listed_pronunciation(summary, groups) or summary.pronunciation
    return make_card(entry, Card(pronunciation=pronunciation, respelling=summary.respelling,
                                 meaning=summary.meaning))


def letters(text):
    """Return text folded to its letters and digits, so quote marks and accents do not matter."""
    return "".join(c for c in vocab.fold(text) if c.isalnum())


def fits(batch, entries, groups):
    """Return True if the cards are for exactly these entries, in order, each naming one of its groups or
    0 where several are listed (elsewhere the group is not used)."""
    return ([letters(card.entry) for card in batch.cards] == [letters(entry) for entry in entries]
            and all(len(g) < 2 or 0 <= card.group <= len(g) for card, g in zip(batch.cards, groups)))


@retrying
def card_summaries(entries):
    """Return a card dict (entry, pronunciation, respelling, meaning) for each entry.

    The pronunciation is Wiktionary's British IPA where it has one. Where it has several, the
    model picks the group whose senses include the meaning it wrote; it never retypes the IPA.
    """
    groups = [dictionary.lookup(entry) for entry in entries]
    listing = "\n".join(f"{i}. {entry}\n{pronunciation_listing(g)}"
                        for i, (entry, g) in enumerate(zip(entries, groups), 1))
    batch = ask(CARD_PROMPT.format(entries=listing), CardBatch, valid=lambda reply: fits(reply, entries, groups))
    return [summary_card(entry, card, g) for entry, card, g in zip(entries, batch.cards, groups)]


@retrying
def choose_quotes(entry, meaning, candidates):
    """Return up to 3 of the candidate quotes that use the entry well, best first."""
    if not candidates:
        return []
    listing = "\n".join(f"{i}. {c['text']}" for i, c in enumerate(candidates, 1))
    choice = ask(CHOOSE_PROMPT.format(entry=entry, meaning=meaning, listing=listing), Choice,
                 valid=lambda reply: all(1 <= n <= len(candidates) for n in reply.chosen))
    return [candidates[n - 1] for n in dict.fromkeys(choice.chosen)]


def revision_input(entry):
    """Return the entry's current content as the JSON shown to the LLM for revision."""
    detail = entry["detail"]
    quotes = [e for e in detail["examples"] if e["source"]]
    current = {
        "pronunciation": entry["pronunciation"], "respelling": entry["respelling"],
        "meaning": entry["meaning"], "senses": detail["senses"],
        "guardian_quotes": [{"number": n, "text": q["text"]} for n, q in enumerate(quotes, 1)],
        "written_examples": [e["text"] for e in detail["examples"] if not e["source"]],
        "synonyms": detail["synonyms"], "antonyms": detail["antonyms"],
    }
    return json.dumps(current, ensure_ascii=False, indent=1), quotes


def quotes_to_drop(revision):
    """Return the quote numbers to drop: only those named when the model says the feedback asked."""
    return revision.drop_quotes if revision.feedback_asks_to_remove_quotes else []


@retrying
def revise(entry, feedback, max_examples):
    """Apply learner feedback; return the revised card fields and detail.

    Written examples that repeat a Guardian quote are dropped: gpt-4o-mini returned a quote among
    them in 2 of 7 unrelated revisions, which then showed twice, once as an "Example sentence".
    """
    current, quotes = revision_input(entry)
    prompt = REVISE_PROMPT.format(entry=entry["entry"], current=current, feedback=feedback,
                                  max_examples=max_examples)
    revision = ask(prompt, Revision,
                   valid=lambda reply: all(1 <= n <= len(quotes) for n in quotes_to_drop(reply)))
    kept = [q for n, q in enumerate(quotes, 1) if n not in quotes_to_drop(revision)]
    quoted = {letters(q["text"]) for q in quotes}
    written = [{"text": t, "source": None} for t in revision.written_examples if letters(t) not in quoted]
    if revision.feedback_asks_to_change_pronunciation:
        pronunciation, respelling = revision.pronunciation, revision.respelling
    else:
        pronunciation, respelling = entry["pronunciation"], entry["respelling"]
    card = make_card(entry["entry"], Card(pronunciation=pronunciation, respelling=respelling,
                                          meaning=revision.meaning))
    detail = {"senses": [s.model_dump() for s in revision.senses],
              "examples": (kept + written)[:max_examples],
              "synonyms": revision.synonyms, "antonyms": revision.antonyms}
    return card, detail


@retrying
def entry_detail(entry):
    """Return all senses and example sentences for one entry as a dict."""
    return ask(DETAIL_PROMPT.format(entry=entry), Detail).model_dump()
