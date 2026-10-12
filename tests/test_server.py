"""HTTP behaviour: error messages, local-only access, the PDF route and stopping when pages close."""
import io
import time
import urllib.error
from types import SimpleNamespace

import litellm
import pytest
from fastapi.testclient import TestClient

import config
import journal
import server
from conftest import TODAY, add_on, groq_invalid_key

LOCAL = "http://127.0.0.1:8000"


@pytest.fixture
def client():
    return TestClient(server.app, base_url=LOCAL, raise_server_exceptions=False)


def test_unknown_entry_returns_readable_error(client):
    response = client.get("/api/entries/9999/detail")
    assert response.status_code == 400
    assert response.json() == {"error": "That entry no longer exists. Reload the page."}


def test_accept_round_trip_and_pdf(client):
    assert client.get("/api/pdf").json()["error"].startswith("No accepted entries")
    entry_id = add_on(TODAY, "abase")
    assert client.post(f"/api/entries/{entry_id}/accept", headers={"Origin": LOCAL}).json()["accepted"]
    assert client.get("/api/pdf").headers["content-type"] == "application/pdf"
    assert [e["entry"] for e in client.get("/api/accepted").json()] == ["abase"]


def test_pdf_head_reports_availability_without_body(client):
    assert client.head("/api/pdf").status_code == 400
    journal.accept(add_on(TODAY, "abase"))
    response = client.head("/api/pdf")
    assert (response.status_code, response.headers["content-type"], response.content) ==         (200, "application/pdf", b"")


def test_blank_typed_entry_returns_readable_error(client):
    response = client.post("/api/today/add", json={"entry": "  "}, headers={"Origin": LOCAL})
    assert (response.status_code, response.json()) == (400, {"error": "Type a word or phrase to look up."})


def test_requests_from_other_sites_are_refused(client):
    assert client.post("/api/today/more", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/today", headers={"Host": "evil.example:8000"}).status_code == 403
    assert client.get("/api/days").status_code == 200


def raise_from_detail(monkeypatch, error):
    def detail(entry_id):
        raise error
    monkeypatch.setattr(journal, "detail", detail)


@pytest.mark.parametrize("error, message", [
    (urllib.error.HTTPError("u", 403, "x", {}, io.BytesIO()), "rejected GUARDIAN_API_KEY"),
    (urllib.error.HTTPError("u", 429, "x", {}, io.BytesIO()), "request limit"),
    (urllib.error.URLError("down"), "Could not reach The Guardian"),
    (litellm.AuthenticationError("x", llm_provider="groq", model="m"), "groq provider rejected its API key"),
    (litellm.AuthenticationError("x", llm_provider="openai", model="m"), "openai provider rejected its API key"),
    (litellm.NotFoundError("x", llm_provider="openai", model="gpt-x"), "does not know the model gpt-x"),
    (groq_invalid_key(), "groq provider rejected its API key"),
    (litellm.RateLimitError("x", llm_provider="openai", model="m"), "Both LLM services failed"),
])
def test_service_failures_return_readable_errors(client, monkeypatch, error, message):
    raise_from_detail(monkeypatch, error)
    response = client.get("/api/entries/1/detail")
    assert response.status_code == 502
    assert message in response.json()["error"]


def test_missing_settings_are_named(monkeypatch):
    monkeypatch.setattr(config, "LLM_MODEL", "")
    monkeypatch.setattr(config, "LLM_FALLBACK_MODEL", "")
    monkeypatch.setattr(config, "GUARDIAN_API_KEY", "")
    assert config.missing_settings() == ["LLM_MODEL", "LLM_FALLBACK_MODEL", "GUARDIAN_API_KEY"]


def use_groq_with_openai_fallback(monkeypatch):
    monkeypatch.setattr(config, "LLM_MODEL", "groq/openai/gpt-oss-120b")
    monkeypatch.setattr(config, "LLM_FALLBACK_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setattr(config, "GUARDIAN_API_KEY", "k")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("OPENAI_API_KEY", "k")


def test_missing_fallback_provider_key_is_named(monkeypatch):
    use_groq_with_openai_fallback(monkeypatch)
    monkeypatch.delenv("OPENAI_API_KEY")
    assert config.missing_settings() == ["OPENAI_API_KEY"]


def test_blank_provider_key_in_env_file_is_named(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("GROQ_API_KEY=\n")
    use_groq_with_openai_fallback(monkeypatch)
    monkeypatch.delenv("GROQ_API_KEY")
    config.load_env_file(env_file)
    assert config.missing_settings() == ["GROQ_API_KEY"]


def test_missing_provider_key_is_named(monkeypatch):
    use_groq_with_openai_fallback(monkeypatch)
    monkeypatch.delenv("GROQ_API_KEY")
    assert config.missing_settings() == ["GROQ_API_KEY"]


@pytest.fixture
def running(monkeypatch):
    """A stand-in for the uvicorn server, with no grace period."""
    monkeypatch.setattr(server, "CLOSE_GRACE", 0)
    monkeypatch.setattr(server, "OPEN_PAGES", set())
    monkeypatch.setattr(server, "SERVER", SimpleNamespace(should_exit=False))
    return server.SERVER


def closed_and_waited(client, page_id):
    client.post(f"/api/pages/{page_id}/close")
    time.sleep(0.2)


def test_app_stops_when_the_last_page_closes(client, running):
    client.post("/api/pages/a/open")
    client.post("/api/pages/b/open")
    closed_and_waited(client, "a")
    assert not running.should_exit
    closed_and_waited(client, "b")
    assert running.should_exit


def test_page_reopened_within_the_grace_period_keeps_the_app_running(client, running, monkeypatch):
    monkeypatch.setattr(server, "CLOSE_GRACE", 0.3)
    client.post("/api/pages/a/open")
    client.post("/api/pages/a/close")
    client.post("/api/pages/b/open")
    time.sleep(0.5)
    assert not running.should_exit
