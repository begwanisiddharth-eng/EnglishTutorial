"""Real example sentences from The Guardian Open Platform API."""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

import config

SEARCH_URL = "https://content.guardianapis.com/search"
ARTICLES = 30
MAX_CANDIDATES = 25
PER_ARTICLE = 2
APOSTROPHE = "['’]"
POSSESSIVE = rf"(?:\w+{APOSTROPHE}s|his|her|its|their|my|your|our)"
PLACEHOLDERS = {
    "one's": POSSESSIVE,
    "someone's": POSSESSIVE,
    "oneself": r"\w+(?:self|selves)",
    "someone": r"\w+(?:\s\w+)?",
    "something": r"\w+(?:\s\w+)?",
}
ARTICLE_WORDS = {"a", "an", "the"}
SENTENCE_END = re.compile(r"(?<=[.!?])[\"”’]?\s+(?=[\"“‘A-Z])")


def core_words(entry):
    """Return the entry's words without a leading article."""
    words = entry.split()
    if len(words) > 1 and words[0].lower() in ARTICLE_WORDS:
        return words[1:]
    return words


def inflectable(word):
    """Return a regex matching a word and its common inflections."""
    if word.endswith("ing") and len(word) > 5:
        stem = word[:-3]
    elif word.endswith("e") and len(word) > 4:
        stem = word[:-1]
    else:
        stem = word
    return re.escape(stem).replace("'", APOSTROPHE) + r"\w{0,4}"


def transient(error):
    """Return True for failures worth retrying: network errors, rate limits and server errors."""
    if isinstance(error, urllib.error.HTTPError):
        return error.code == 429 or error.code >= 500
    return isinstance(error, urllib.error.URLError)


def literal(word):
    """Return a regex matching a word exactly, allowing either apostrophe style."""
    return PLACEHOLDERS.get(word.lower(), re.escape(word).replace("'", APOSTROPHE))


def entry_pattern(entry):
    """Return a case-insensitive regex that finds the entry in running text."""
    first, *rest = core_words(entry)
    head = literal(first) if first.lower() in PLACEHOLDERS else inflectable(first)
    parts = [head] + [literal(w) for w in rest]
    return re.compile(r"\b" + r"\s+".join(parts) + r"\b", re.IGNORECASE)


def search_query(entry):
    """Return an API query requiring every fixed part of the entry, each as a quoted phrase."""
    runs, current = [], []
    for word in core_words(entry):
        if word.lower() in PLACEHOLDERS:
            runs.append(current)
            current = []
        else:
            current.append(word)
    runs.append(current)
    return " AND ".join(f'"{" ".join(run)}"' for run in runs if run)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20), reraise=True,
       retry=retry_if_exception(transient))
def search(query):
    """Return Guardian articles (title, url, date, body text) matching the query."""
    query = urllib.parse.urlencode({
        "q": query, "show-fields": "bodyText", "page-size": ARTICLES,
        "api-key": config.GUARDIAN_API_KEY,
    })
    with urllib.request.urlopen(f"{SEARCH_URL}?{query}", timeout=30) as response:
        results = json.load(response)["response"]["results"]
    return [{"title": r["webTitle"], "url": r["webUrl"], "date": r["webPublicationDate"][:10],
             "text": r.get("fields", {}).get("bodyText", "")} for r in results]


def candidates(entry, articles):
    """Return sentences of sensible length that contain the entry, with their source."""
    pattern = entry_pattern(entry)
    found = []
    for article in articles:
        matches = [s for s in SENTENCE_END.split(article["text"])
                   if pattern.search(s) and 8 <= len(s.split()) <= 45]
        found += [{"text": s.strip(), "source": "The Guardian", "title": article["title"],
                   "url": article["url"], "date": article["date"]} for s in matches[:PER_ARTICLE]]
    return found[:MAX_CANDIDATES]
