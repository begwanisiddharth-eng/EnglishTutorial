"""LLM reply handling and retry rules, with completion() stubbed."""
from types import SimpleNamespace

import litellm
import pytest
import tenacity

import llm
from conftest import groq_invalid_key


def reply(json_text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json_text))])


def stub_completion(monkeypatch, outcomes):
    """Make completion() return or raise each outcome in turn; return the list of calls."""
    calls = []

    def completion(**kwargs):
        calls.append(kwargs)
        outcome = outcomes[len(calls) - 1]
        if isinstance(outcome, BaseException):
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
    groq_invalid_key(),
])
def test_permanent_errors_are_not_retried(monkeypatch, error):
    calls = stub_completion(monkeypatch, [error] * 4)
    with pytest.raises(type(error)):
        llm.entry_detail("abate")
    assert len(calls) == 1


def test_keyboard_interrupt_is_not_retried(monkeypatch):
    calls = stub_completion(monkeypatch, [KeyboardInterrupt()] * 4)
    with pytest.raises(KeyboardInterrupt):
        llm.entry_detail("abate")
    assert len(calls) == 1


DETAIL_REPLY = ('{"senses": [{"part_of_speech": "verb", "definition": "d"}], "examples": ["e"],'
                ' "synonyms": [], "antonyms": []}')


class FakeClock:
    """A clock that tenacity reads and that its sleeps advance, so retry timing runs instantly."""

    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def rate_limited_for(monkeypatch, seconds):
    """Make completion() fail with a rate limit until the fake clock passes seconds; return the calls."""
    clock = FakeClock()
    monkeypatch.setattr(tenacity, "time", clock)
    monkeypatch.setattr(llm.entry_detail.retry, "sleep", clock.sleep)
    calls = []

    def completion(**kwargs):
        calls.append(clock.now)
        if clock.now < seconds:
            raise litellm.RateLimitError("tokens per minute", llm_provider="groq", model="m")
        return reply(DETAIL_REPLY)

    monkeypatch.setattr(llm, "completion", completion)
    return calls


def test_rate_limit_lasting_a_minute_is_waited_out(monkeypatch):
    calls = rate_limited_for(monkeypatch, 60)
    assert llm.entry_detail("abate")["examples"] == ["e"]
    assert calls[-1] >= 60


def test_endless_rate_limit_gives_up_within_budget(monkeypatch):
    calls = rate_limited_for(monkeypatch, float("inf"))
    with pytest.raises(litellm.RateLimitError):
        llm.entry_detail("abate")
    assert len(calls) <= llm.MAX_ATTEMPTS
    assert calls[-1] <= llm.RETRY_SECONDS
