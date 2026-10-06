"""LLM reply handling and retry rules, with completion() stubbed."""
from types import SimpleNamespace

import litellm
import pytest

import llm
from conftest import FALLBACK, PRIMARY, groq_daily_limit, groq_invalid_key


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


DETAIL_REPLY = ('{"senses": [{"part_of_speech": "verb", "definition": "d"}], "examples": ["e"],'
                ' "synonyms": [], "antonyms": []}')


def test_primary_answers_without_touching_the_fallback(monkeypatch):
    calls = stub_completion(monkeypatch, [DETAIL_REPLY])
    assert llm.entry_detail("abate")["senses"][0]["definition"] == "d"
    assert [(c["model"], c["timeout"], c["max_retries"]) for c in calls] == [
        (PRIMARY, llm.PRIMARY_TIMEOUT_SECONDS, 0)]


@pytest.mark.parametrize("failure", [
    litellm.RateLimitError("tokens per minute (TPM)", llm_provider="groq", model="m"),
    groq_daily_limit(),
    litellm.ServiceUnavailableError("over capacity", llm_provider="groq", model="m"),
    litellm.Timeout("timed out", llm_provider="groq", model="m"),
    litellm.APIConnectionError("no route", llm_provider="groq", model="m"),
    litellm.BadRequestError("json_validate_failed", llm_provider="groq", model="m"),
    "not json",
])
def test_primary_failure_switches_to_fallback_at_once(monkeypatch, caplog, failure):
    sleeps = []
    monkeypatch.setattr(llm.entry_detail.retry, "sleep", sleeps.append)
    calls = stub_completion(monkeypatch, [failure, DETAIL_REPLY])
    assert llm.entry_detail("abate")["examples"] == ["e"]
    assert [(c["model"], c["timeout"]) for c in calls] == [
        (PRIMARY, llm.PRIMARY_TIMEOUT_SECONDS), (FALLBACK, llm.FALLBACK_TIMEOUT_SECONDS)]
    assert sleeps == []
    assert f"using {FALLBACK}" in caplog.text


def test_choose_quotes_retries_out_of_range_numbers(monkeypatch):
    calls = stub_completion(monkeypatch, ['{"chosen": [7]}', '{"chosen": [2, 2]}'])
    candidates = [{"text": "a"}, {"text": "b"}]
    assert llm.choose_quotes("x", "m", candidates) == [{"text": "b"}]
    assert len(calls) == 2


def entry_with_quotes(count):
    """Return an opened entry with count Guardian quotes and one written example."""
    quotes = [{"text": f"quote {n}", "source": "The Guardian", "title": "t", "url": "u", "date": "2025-01-02"}
              for n in range(1, count + 1)]
    return {"entry": "abate", "pronunciation": "/x/", "respelling": "X", "meaning": "m",
            "detail": {"senses": [], "examples": quotes + [{"text": "w", "source": None}],
                       "synonyms": [], "antonyms": []}}


def revision_reply(**quote_fields):
    return ('{"pronunciation": "/x/", "respelling": "X", "meaning": "shorter", "senses": [],'
            ' "written_examples": ["w"], "synonyms": [], "antonyms": [], '
            + ", ".join(f'"{k}": {v}' for k, v in quote_fields.items()) + "}")


def test_revise_keeps_quotes_the_reply_does_not_mention(monkeypatch):
    stub_completion(monkeypatch, [revision_reply(keep_quotes=[], drop_quotes=[],
                                                 feedback_asks_to_remove_quotes="false")])
    _, detail = llm.revise(entry_with_quotes(3), "shorten the meaning", 5)
    assert [e["text"] for e in detail["examples"]] == ["quote 1", "quote 2", "quote 3", "w"]


def test_revise_ignores_drops_the_feedback_did_not_ask_for(monkeypatch):
    stub_completion(monkeypatch, [revision_reply(drop_quotes=[2], feedback_asks_to_remove_quotes="false")])
    _, detail = llm.revise(entry_with_quotes(3), "shorten the meaning", 5)
    assert [e["text"] for e in detail["examples"]] == ["quote 1", "quote 2", "quote 3", "w"]


def test_revise_drops_only_the_quotes_named(monkeypatch):
    stub_completion(monkeypatch, [revision_reply(drop_quotes=[2], feedback_asks_to_remove_quotes="true")])
    _, detail = llm.revise(entry_with_quotes(3), "drop the second quote", 5)
    assert [e["text"] for e in detail["examples"]] == ["quote 1", "quote 3", "w"]


def test_primary_reply_with_wrong_content_switches_to_fallback(monkeypatch):
    card = '{"pronunciation": "/x/", "respelling": "X", "meaning": "m"}'
    calls = stub_completion(monkeypatch, [f'{{"cards": [{card}]}}', f'{{"cards": [{card}, {card}]}}'])
    assert len(llm.card_summaries(["abate", "abase"])) == 2
    assert [c["model"] for c in calls] == [PRIMARY, FALLBACK]


@pytest.mark.parametrize("error", [
    litellm.AuthenticationError("bad key", llm_provider="groq", model="m"),
    litellm.NotFoundError("no model", llm_provider="groq", model="m"),
    groq_invalid_key(),
])
def test_configuration_errors_are_reported_not_hidden_by_the_fallback(monkeypatch, error):
    calls = stub_completion(monkeypatch, [error] * 4)
    with pytest.raises(type(error)):
        llm.entry_detail("abate")
    assert len(calls) == 1


def test_fallback_configuration_error_is_reported_at_once(monkeypatch):
    bad_key = litellm.AuthenticationError("bad key", llm_provider="openai", model="m")
    calls = stub_completion(monkeypatch, [litellm.RateLimitError("tpm", llm_provider="groq", model="m"), bad_key])
    with pytest.raises(litellm.AuthenticationError):
        llm.entry_detail("abate")
    assert [c["model"] for c in calls] == [PRIMARY, FALLBACK]


def test_keyboard_interrupt_is_not_retried(monkeypatch):
    calls = stub_completion(monkeypatch, [KeyboardInterrupt()] * 4)
    with pytest.raises(KeyboardInterrupt):
        llm.entry_detail("abate")
    assert len(calls) == 1


def test_both_failing_gives_up_after_a_bounded_number_of_tries(monkeypatch):
    sleeps = []
    monkeypatch.setattr(llm.entry_detail.retry, "sleep", sleeps.append)
    busy = litellm.RateLimitError("tpm", llm_provider="groq", model="m")
    calls = stub_completion(monkeypatch, [busy] * (2 * llm.MAX_ATTEMPTS))
    with pytest.raises(litellm.RateLimitError):
        llm.entry_detail("abate")
    assert [c["model"] for c in calls] == [PRIMARY, FALLBACK] * llm.MAX_ATTEMPTS
    assert sum(sleeps) <= 5
