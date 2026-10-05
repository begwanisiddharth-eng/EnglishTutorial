"""Settings read once from .env in the project folder."""
import os
from pathlib import Path

from dotenv import load_dotenv
from litellm import validate_environment

load_dotenv(Path(__file__).parent / ".env")

LLM_MODEL = os.environ.get("LLM_MODEL", "")
GUARDIAN_API_KEY = os.environ.get("GUARDIAN_API_KEY", "")


def missing_settings():
    """Return the names of settings .env must provide but does not, including the LLM provider's key."""
    missing = [name for name, value in (("LLM_MODEL", LLM_MODEL), ("GUARDIAN_API_KEY", GUARDIAN_API_KEY))
               if not value]
    if LLM_MODEL:
        missing += validate_environment(LLM_MODEL)["missing_keys"]
    return missing
