"""Local web server for the vocabulary app. Run with: uv run server.py"""
import ctypes
import sys
import threading
import urllib.error
import webbrowser
from pathlib import Path

import openai
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
import db
import journal
import pdf

STATIC = Path(__file__).parent / "static"
PORT = 8000
URL = f"http://127.0.0.1:{PORT}"
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
CLOSE_GRACE = 5  # seconds to wait after the last page closes, so a reload does not stop the app
OPEN_PAGES = set()
SERVER = None  # the uvicorn server when run as a program; tests leave it None

app = FastAPI()
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class TypedEntry(BaseModel):
    """An entry the user typed in."""
    entry: str


class Feedback(BaseModel):
    """The learner's request for changes to an entry."""
    feedback: str


def error(status, message):
    """Return an error message in the form the page shows as a toast."""
    return JSONResponse(status_code=status, content={"error": message})


@app.middleware("http")
async def local_only(request: Request, call_next):
    """Refuse requests from other web pages or under another host name (DNS rebinding)."""
    origin = request.headers.get("origin")
    if (request.headers.get("host") not in ALLOWED_HOSTS
            or (origin is not None and origin.removeprefix("http://") not in ALLOWED_HOSTS)):
        return error(403, "Requests from other sites are not allowed.")
    return await call_next(request)


@app.middleware("http")
async def no_cache(request: Request, call_next):
    """Make the browser revalidate every file, so updated pages are never mixed with stale ones."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.exception_handler(journal.Refused)
def refused(request: Request, exc: journal.Refused):
    """Report a disallowed action to the page as an error message."""
    return error(400, str(exc))


@app.exception_handler(urllib.error.HTTPError)
def guardian_refused(request: Request, exc: urllib.error.HTTPError):
    """Explain an error status from The Guardian API."""
    if exc.code in (401, 403):
        return error(502, "The Guardian rejected GUARDIAN_API_KEY. Check it in .env.")
    if exc.code == 429:
        return error(502, "The Guardian's request limit has been reached. Try again later.")
    return error(502, f"The Guardian returned an error ({exc.code}). Try again later.")


@app.exception_handler(urllib.error.URLError)
def guardian_unreachable(request: Request, exc: urllib.error.URLError):
    """Explain a network failure reaching The Guardian."""
    return error(502, "Could not reach The Guardian. Check the internet connection.")


@app.exception_handler(openai.APIError)
def llm_failed(request: Request, exc: openai.APIError):
    """Explain an LLM failure (all litellm errors derive from openai.APIError), judged by its HTTP status.

    Rate limits and outages of the primary model never get here: llm.ask switches to the fallback.
    """
    status = getattr(exc, "status_code", None)
    provider = getattr(exc, "llm_provider", None) or "LLM"
    if status in (401, 403):
        return error(502, f"The {provider} provider rejected its API key in .env.")
    if status == 404:
        return error(502, f"The {provider} provider does not know the model {getattr(exc, 'model', '')}. "
                          "Check LLM_MODEL and LLM_FALLBACK_MODEL in .env.")
    return error(502, "Both LLM services failed. Try again in a minute.")


@app.get("/")
def index():
    """Serve the single-page app."""
    return FileResponse(STATIC / "index.html")


@app.post("/api/pages/{page_id}/open")
def page_opened(page_id: str):
    """Record a page as open."""
    OPEN_PAGES.add(page_id)


@app.post("/api/pages/{page_id}/close")
def page_closed(page_id: str):
    """Record a page as closed; once none is open, stop the app after a short grace period."""
    OPEN_PAGES.discard(page_id)
    if not OPEN_PAGES:
        threading.Timer(CLOSE_GRACE, stop_if_unused).start()


def stop_if_unused():
    """Stop the server if no page has opened since the last one closed."""
    if SERVER and not OPEN_PAGES and not SERVER.should_exit:
        SERVER.should_exit = True
        print("The Word Bank page was closed, so the app has stopped.")


@app.get("/api/today")
def today():
    """Return today's date and entries."""
    return {"day": journal.today(), "entries": journal.todays_entries()}


@app.post("/api/today/more")
def more():
    """Add five more random entries to today."""
    journal.add_random(journal.DAILY_COUNT)
    return journal.todays_entries()


@app.post("/api/today/add")
def add(typed: TypedEntry):
    """Add a typed entry to today."""
    journal.add_typed(typed.entry)
    return journal.todays_entries()


@app.get("/api/days")
def days():
    """Return the days to show in the calendar."""
    return db.visible_days(journal.today())


@app.get("/api/days/{day}")
def day(day: str):
    """Return the entries shown for one day."""
    return journal.day_entries(day)


@app.get("/api/accepted")
def accepted():
    """Return every accepted entry alphabetically."""
    return db.accepted_entries()


@app.api_route("/api/pdf", methods=["GET", "HEAD"])
def download_pdf():
    """Return the PDF of accepted entries."""
    if not pdf.PDF_PATH.exists():
        raise journal.Refused("No accepted entries yet, so there is no PDF.")
    return FileResponse(pdf.PDF_PATH, media_type="application/pdf")


@app.get("/api/entries/{entry_id}/detail")
def detail(entry_id: int):
    """Return one entry with its detail."""
    return journal.detail(entry_id)


@app.post("/api/entries/{entry_id}/revise")
def revise(entry_id: int, body: Feedback):
    """Revise an entry according to feedback."""
    return journal.revise(entry_id, body.feedback)


@app.post("/api/entries/{entry_id}/accept")
def accept(entry_id: int):
    """Accept an entry as final."""
    return journal.accept(entry_id)


@app.delete("/api/entries/{entry_id}")
def delete(entry_id: int):
    """Delete an entry under the daily-page rules."""
    journal.delete(entry_id)
    return {"ok": True}


def disable_quick_edit():
    """Turn off QuickEdit for this console window. While text is selected in it, Windows blocks every
    write to the console, and the app's logging with it, so a stray click froze the whole app."""
    console = ctypes.windll.kernel32
    handle = console.GetStdHandle(-10)  # standard input
    mode = ctypes.c_ulong()
    console.GetConsoleMode(handle, ctypes.byref(mode))
    console.SetConsoleMode(handle, (mode.value & ~0x40) | 0x80)  # clear QuickEdit, keep the setting


if __name__ == "__main__":
    if missing := config.missing_settings():
        sys.exit("Add these settings to the .env file, then start again: " + ", ".join(missing))
    if sys.platform == "win32":
        disable_quick_edit()
    threading.Timer(1.5, webbrowser.open, [URL]).start()
    SERVER = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT))
    SERVER.run()
