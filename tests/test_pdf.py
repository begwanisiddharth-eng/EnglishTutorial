"""The PDF of accepted entries."""
import pytest

import pdf
import vocab
from conftest import ARTICLE_DATE


def accepted(text, url="https://www.theguardian.com/x"):
    """Return an accepted entry with one Guardian quote and one written example."""
    quote = {"text": f"A quote with {text}.", "source": "The Guardian", "title": "T", "url": url,
             "date": ARTICLE_DATE}
    return {"entry": text, "respelling": "X", "pronunciation": "/x/", "meaning": "m",
            "detail": {"senses": [{"part_of_speech": "verb", "definition": "d"}],
                       "examples": [quote, {"text": "Written.", "source": None}],
                       "synonyms": ["s"], "antonyms": []}}


def test_words_come_before_phrases_at_realistic_size():
    words = vocab.master_list()[:240]
    phrases = vocab.master_list()[vocab.WORD_COUNT:vocab.WORD_COUNT + 60]
    pdf.build([accepted(e) for e in phrases + words])
    data = pdf.PDF_PATH.read_bytes()
    assert data.index(b"(Words)") < data.index(b"(Phrases)")
    assert data.index(f"({words[-1]})".encode()) < data.index(b"(Phrases)") < data.index(f"({phrases[0]})".encode())
    assert not pdf.TEMP_PATH.exists()


@pytest.mark.parametrize("text", ["a baker's dozen", "one's bark is worse than one's bite", 'say "when"',
                                  "rock & roll", "a < b"])
def test_headings_with_quotes_and_markup_characters_build(text):
    pdf.build([accepted(text), accepted("abase")])
    data = pdf.PDF_PATH.read_bytes()
    assert f"({text})".encode() in data
    headings = 4 if vocab.is_phrase(text) else 3
    assert data.count(b"/Dest [") == 3 * headings  # two contents links and one outline entry each


def test_link_url_with_quote_is_kept_whole():
    url = 'https://x.example/?a="b'
    pdf.build([accepted("abase", url)])
    assert f"/URI ({url})".encode() in pdf.PDF_PATH.read_bytes()


def test_no_entries_removes_the_pdf():
    pdf.build([accepted("abase")])
    pdf.build([])
    assert not pdf.PDF_PATH.exists()
