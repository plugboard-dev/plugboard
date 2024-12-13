#!/usr/bin/env bash
git config --global --add safe.directory $(pwd)
uv venv
uv sync
uv run pre-commit install
