"""LLM reply handling and retry rules, with completion() stubbed."""
from types import SimpleNamespace

import litellm
import pytest

import llm


def reply(json_text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json_text))])


def stub_completion(monkeypatch, outcomes):
    """Make completion() return or raise each outcome in turn; return the list of calls."""
    calls = []

    def completion(**kwargs):
        calls.append(kwargs)
        outcome = outcomes[len(calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return reply(outcome)

    monkeypatch.setattr(llm, "completion", completion)
    return calls


def test_detail_is_parsed_and_sent_with_timeout(monkeypatch):
    calls = stub_completion(monkeypatch, [
        '{"senses": [{"part_of_speech": "verb", "definition": "d"}], "examples": ["e"],'
        ' "synonyms": [], "antonyms": []}'])
    assert llm.entry_detail("abate")["senses"][0]["definition"] == "d"
    assert calls[0]["timeout"] == llm.TIMEOUT_SECONDS


def test_choose_quotes_retries_out_of_range_numbers(monkeypatch):
    calls = stub_completion(monkeypatch, ['{"chosen": [7]}', '{"chosen": [2, 2]}'])
    candidates = [{"text": "a"}, {"text": "b"}]
    assert llm.choose_quotes("x", "m", candidates) == [{"text": "b"}]
    assert len(calls) == 2


@pytest.mark.parametrize("error", [
    litellm.AuthenticationError("bad key", llm_provider="groq", model="m"),
    litellm.NotFoundError("no model", llm_provider="groq", model="m"),
])
def test_permanent_errors_are_not_retried(monkeypatch, error):
    calls = stub_completion(monkeypatch, [error] * 4)
    with pytest.raises(type(error)):
        llm.entry_detail("abate")
    assert len(calls) == 1


def test_rate_limit_is_retried(monkeypatch):
    error = litellm.RateLimitError("slow down", llm_provider="groq", model="m")
    calls = stub_completion(monkeypatch, [error] * 4)
    with pytest.raises(litellm.RateLimitError):
        llm.entry_detail("abate")
    assert len(calls) == 4
