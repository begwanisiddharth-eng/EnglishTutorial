"""LLM reply handling and retry rules, with completion() stubbed."""
import json
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


def revision_reply(**gates):
    """Return a revision that rewrites the pronunciation, with the given quote and pronunciation fields."""
    gates = {"feedback_asks_to_change_pronunciation": "false", **gates}
    return ('{"pronunciation": "/new/", "respelling": "NEW", "meaning": "shorter", "senses": [],'
            ' "written_examples": ["w"], "synonyms": [], "antonyms": [], '
            + ", ".join(f'"{k}": {v}' for k, v in gates.items()) + "}")


@pytest.mark.parametrize("asks, expected", [("false", ("/x/", "X")), ("true", ("/new/", "NEW"))])
def test_revise_keeps_the_pronunciation_unless_the_feedback_asks(monkeypatch, asks, expected):
    stub_completion(monkeypatch, [revision_reply(drop_quotes=[], feedback_asks_to_remove_quotes="false",
                                                 feedback_asks_to_change_pronunciation=asks)])
    card, _ = llm.revise(entry_with_quotes(1), "shorten the meaning", 5)
    assert (card["pronunciation"], card["respelling"]) == expected
    assert card["meaning"] == "shorter"


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


def cards_reply(*cards):
    """Return a card batch reply with one card per (entry, group, pronunciation)."""
    return json.dumps({"cards": [{"entry": entry, "meaning": f"meaning of {entry}", "group": group,
                                  "pronunciation": pronunciation, "respelling": "R"}
                                 for entry, group, pronunciation in cards]})


@pytest.mark.parametrize("wrong", [
    [("abate", 0, "/x/")],
    [("abate", 0, "/x/"), ("abase", 0, "/x/"), ("abase", 0, "/y/")],
    [("abase", 0, "/x/"), ("abate", 0, "/x/")],
], ids=["card missing", "extra card for one entry", "cards swapped"])
def test_primary_reply_with_wrong_content_switches_to_fallback(monkeypatch, wrong):
    calls = stub_completion(monkeypatch, [cards_reply(*wrong), cards_reply(("abate", 0, "/x/"), ("Abase", 0, "/x/"))])
    assert [c["meaning"] for c in llm.card_summaries(["abate", "abase"])] == ["meaning of abate", "meaning of Abase"]
    assert [c["model"] for c in calls] == [PRIMARY, FALLBACK]


def test_cards_match_entries_whatever_the_quote_marks_and_accents(monkeypatch):
    stub_completion(monkeypatch, [cards_reply(("raison d’etat", 0, "/x/"))])
    assert llm.card_summaries(["raison d'état"])[0]["entry"] == "raison d'état"


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


BUFFET = [{"ipa": "/ˈbʊfeɪ/", "senses": ["(noun) A sideboard."]},
          {"ipa": "", "senses": ["(verb) To strike repeatedly."]}]


def card_reply(group, entry="buffet"):
    return cards_reply((entry, group, "/model/"))


@pytest.mark.parametrize("group, expected", [(1, "/ˈbʊfeɪ/"), (2, "/model/"), (0, "/model/")])
def test_card_takes_the_pronunciation_of_the_chosen_wiktionary_group(monkeypatch, group, expected):
    monkeypatch.setattr(llm.dictionary, "entries", lambda: {"buffet": BUFFET})
    calls = stub_completion(monkeypatch, [card_reply(group)])
    assert llm.card_summaries(["buffet"])[0]["pronunciation"] == expected
    prompt = calls[0]["messages"][0]["content"]
    assert "Wiktionary group 1, pronunciation /ˈbʊfeɪ/:\n     (noun) A sideboard." in prompt
    assert "Wiktionary group 2, no British pronunciation:" in prompt


def test_card_naming_a_group_that_does_not_exist_switches_to_fallback(monkeypatch):
    monkeypatch.setattr(llm.dictionary, "entries", lambda: {"buffet": BUFFET})
    calls = stub_completion(monkeypatch, [card_reply(3), card_reply(1)])
    assert llm.card_summaries(["buffet"])[0]["pronunciation"] == "/ˈbʊfeɪ/"
    assert [c["model"] for c in calls] == [PRIMARY, FALLBACK]


def test_entry_not_in_wiktionary_is_marked_and_keeps_the_model_pronunciation(monkeypatch):
    calls = stub_completion(monkeypatch, [card_reply(0, "abate")])
    assert llm.card_summaries(["abate"])[0]["pronunciation"] == "/model/"
    assert "1. abate\n   (not in Wiktionary)" in calls[0]["messages"][0]["content"]


def test_detail_prompt_lists_wiktionary_senses_only_when_there_are_some(monkeypatch):
    monkeypatch.setattr(llm.dictionary, "entries", lambda: {"buffet": BUFFET})
    calls = stub_completion(monkeypatch, [DETAIL_REPLY, DETAIL_REPLY])
    llm.entry_detail("buffet")
    llm.entry_detail("abate")
    assert "- (noun) A sideboard.\n- (verb) To strike repeatedly." in calls[0]["messages"][0]["content"]
    assert "Wiktionary" not in calls[1]["messages"][0]["content"]
