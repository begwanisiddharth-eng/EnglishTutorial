#!/usr/bin/env sh
# Start Word Bank and open it in the browser. Requires uv: https://docs.astral.sh/uv/
cd "$(dirname "$0")"
uv run server.py
