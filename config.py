"""Settings read once from .env in the project folder."""
import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv
from litellm import validate_environment


def load_env_file(path):
    """Load settings from an env file, treating a blank value ("GROQ_API_KEY=") as unset.

    litellm counts a key as present even when it is blank, so a blank one would pass the startup check.
    """
    load_dotenv(path)
    for name in dotenv_values(path):
        if not os.environ.get(name):
            os.environ.pop(name, None)


load_env_file(Path(__file__).parent / ".env")

LLM_MODEL = os.environ.get("LLM_MODEL", "")
GUARDIAN_API_KEY = os.environ.get("GUARDIAN_API_KEY", "")


def missing_settings():
    """Return the names of settings .env must provide but does not, including the LLM provider's key."""
    missing = [name for name, value in (("LLM_MODEL", LLM_MODEL), ("GUARDIAN_API_KEY", GUARDIAN_API_KEY))
               if not value]
    if LLM_MODEL:
        missing += validate_environment(LLM_MODEL)["missing_keys"]
    return missing
