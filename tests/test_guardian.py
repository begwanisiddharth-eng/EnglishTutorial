"""Guardian query building, sentence matching and retry rules."""
import io
import urllib.error

import pytest

import guardian


@pytest.mark.parametrize("entry, sentence, expected", [
    ("abate", "The storm abated overnight and the roads reopened to traffic.", True),
    ("abate", "The storm was over by morning and the roads reopened.", False),
    ("one's bark is worse than one's bite", "Everyone says his bark is worse than his bite.", True),
    ("bite the bullet", "In the end the minister had to bite the bullet.", True),
    ("a babe in the woods", "He was a babe in the woods when it came to money.", True),
])
def test_entry_pattern(entry, sentence, expected):
    assert bool(guardian.entry_pattern(entry).search(sentence)) is expected


def test_search_query_splits_on_placeholders():
    assert guardian.search_query("one's bark is worse than one's bite") == '"bark is worse than" AND "bite"'
    assert guardian.search_query("a babe in the woods") == '"babe in the woods"'


def test_candidates_keep_sentences_of_sensible_length_with_source():
    article = {"title": "T", "url": "u", "date": "2025-01-02",
               "text": "Too short to abate. The council hopes the noise will abate once the building work ends."}
    found = guardian.candidates("abate", [article])
    assert [c["text"] for c in found] == ["The council hopes the noise will abate once the building work ends."]
    assert found[0]["source"] == "The Guardian"


def http_error(code):
    return urllib.error.HTTPError("u", code, "msg", {}, io.BytesIO(b""))


@pytest.mark.parametrize("error, attempts", [
    (http_error(401), 1), (http_error(403), 1), (http_error(429), 3), (http_error(503), 3),
    (urllib.error.URLError("no network"), 3),
])
def test_search_retries_only_transient_failures(monkeypatch, error, attempts):
    calls = []

    def failing_urlopen(*args, **kwargs):
        calls.append(1)
        raise error

    monkeypatch.setattr(guardian.urllib.request, "urlopen", failing_urlopen)
    with pytest.raises(type(error)):
        guardian.search('"abate"')
    assert len(calls) == attempts
