"""Local web server for the vocabulary app. Run with: uv run server.py"""
import threading
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
import journal
import pdf

STATIC = Path(__file__).parent / "static"
PORT = 8000
URL = f"http://127.0.0.1:{PORT}"

app = FastAPI()
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class TypedEntry(BaseModel):
    """An entry the user typed in."""
    entry: str


class Feedback(BaseModel):
    """The learner's request for changes to an entry."""
    feedback: str


@app.middleware("http")
async def no_cache(request: Request, call_next):
    """Make the browser revalidate every file, so updated pages are never mixed with stale ones."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.exception_handler(journal.Refused)
def refused(request: Request, exc: journal.Refused):
    """Report a disallowed action to the page as an error message."""
    return JSONResponse(status_code=400, content={"error": str(exc)})


@app.get("/")
def index():
    """Serve the single-page app."""
    return FileResponse(STATIC / "index.html")


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


@app.get("/api/pdf")
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


if __name__ == "__main__":
    threading.Timer(1.5, webbrowser.open, [URL]).start()
    uvicorn.run(app, host="127.0.0.1", port=PORT)
