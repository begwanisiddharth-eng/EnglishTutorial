"""LLM calls through LiteLLM, retried with tenacity."""
import json

from litellm import completion
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception, stop_after_attempt, stop_after_delay, wait_exponential

import config

TIMEOUT_SECONDS = 120
# Groq's free tier limits tokens per minute; a rate-limited attempt is refused at once and costs
# nothing, so keep retrying for longer than the one-minute window.
RETRY_SECONDS = 90
MAX_ATTEMPTS = 8
# A rejected key (401, 403) or unknown model (404) will not recover. Judged by status, not exception
# type: litellm reports Groq's "Invalid API Key" as a BadRequestError with status 401.
PERMANENT_STATUS = {401, 403, 404}


def worth_retrying(error):
    """Return True for transient failures and malformed replies; False for permanent errors and interrupts."""
    return isinstance(error, Exception) and getattr(error, "status_code", None) not in PERMANENT_STATUS


retrying = retry(stop=stop_after_attempt(MAX_ATTEMPTS) | stop_after_delay(RETRY_SECONDS),
                 wait=wait_exponential(min=2, max=20), reraise=True, retry=retry_if_exception(worth_retrying))

CARD_PROMPT = """You are a lexicographer writing for advanced learners of English.
For each entry below (a word, phrase, idiom, allusion, or foreign expression
used in English), give:
- pronunciation: the British English (Received Pronunciation) IPA transcription
  as given by the Oxford or Cambridge dictionaries, between slashes, with
  correct primary and secondary stress marks. For foreign expressions, give the
  pronunciation British English speakers use.
- respelling: the same pronunciation as a simple respelling for readers who do
  not know IPA. Syllables joined by hyphens, the stressed syllable in capitals,
  words separated by spaces. Use sh as in shoe, ch as in church, zh as in
  measure, th as in thin. Examples: manumit -> man-yoo-MIT,
  volatile -> VOL-uh-tyle, faute de mieux -> foht duh MYUR.
- meaning: a definition of its principal meaning, at most 20 words. Write a
  definition, never an example sentence.

Use British spelling. Return the cards in the same order as the entries.

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

The Guardian quotes are real published sentences: never reword them. You may only
keep or drop them, by number, in keep_quotes.

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
    """A complete revised entry; Guardian quotes are referenced by number only."""
    pronunciation: str
    respelling: str
    meaning: str
    senses: list[Sense]
    keep_quotes: list[int]
    written_examples: list[str]
    synonyms: list[str]
    antonyms: list[str]


class Card(BaseModel):
    """Pronunciation and principal meaning of one entry."""
    pronunciation: str
    respelling: str
    meaning: str


class CardBatch(BaseModel):
    """Cards for a list of entries, in order."""
    cards: list[Card]


def ask(prompt, schema):
    """Send one prompt and parse the reply into the given Pydantic schema."""
    response = completion(
        model=config.LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format=schema,
        timeout=TIMEOUT_SECONDS,
    )
    return schema.model_validate_json(response.choices[0].message.content)


def shows_pronunciation(entry):
    """Return True for entries short enough (one or two words) to show a pronunciation."""
    return len(entry.split()) <= 2


def make_card(entry, card):
    """Combine an entry with its card fields, dropping pronunciation for longer phrases."""
    fields = card.model_dump()
    if not shows_pronunciation(entry):
        fields.update(pronunciation="", respelling="")
    return {"entry": entry, **fields}


@retrying
def card_summaries(entries):
    """Return a card dict (entry, pronunciation, respelling, meaning) for each entry."""
    listing = "\n".join(f"{i}. {entry}" for i, entry in enumerate(entries, 1))
    batch = ask(CARD_PROMPT.format(entries=listing), CardBatch)
    if len(batch.cards) != len(entries):
        raise ValueError(f"expected {len(entries)} cards, got {len(batch.cards)}")
    return [make_card(entry, card) for entry, card in zip(entries, batch.cards)]


@retrying
def choose_quotes(entry, meaning, candidates):
    """Return up to 3 of the candidate quotes that use the entry well, best first."""
    if not candidates:
        return []
    listing = "\n".join(f"{i}. {c['text']}" for i, c in enumerate(candidates, 1))
    choice = ask(CHOOSE_PROMPT.format(entry=entry, meaning=meaning, listing=listing), Choice)
    if not all(1 <= n <= len(candidates) for n in choice.chosen):
        raise ValueError(f"chosen numbers out of range: {choice.chosen}")
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


@retrying
def revise(entry, feedback, max_examples):
    """Apply learner feedback; return the revised card fields and detail."""
    current, quotes = revision_input(entry)
    prompt = REVISE_PROMPT.format(entry=entry["entry"], current=current, feedback=feedback,
                                  max_examples=max_examples)
    revision = ask(prompt, Revision)
    if not all(1 <= n <= len(quotes) for n in revision.keep_quotes):
        raise ValueError(f"quote numbers out of range: {revision.keep_quotes}")
    kept = [quotes[n - 1] for n in dict.fromkeys(revision.keep_quotes)]
    written = [{"text": t, "source": None} for t in revision.written_examples]
    card = make_card(entry["entry"], Card(pronunciation=revision.pronunciation,
                                          respelling=revision.respelling, meaning=revision.meaning))
    detail = {"senses": [s.model_dump() for s in revision.senses],
              "examples": (kept + written)[:max_examples],
              "synonyms": revision.synonyms, "antonyms": revision.antonyms}
    return card, detail


@retrying
def entry_detail(entry):
    """Return all senses and example sentences for one entry as a dict."""
    return ask(DETAIL_PROMPT.format(entry=entry), Detail).model_dump()
