#!/usr/bin/env bash
git config --global --add safe.directory $(pwd)
uv venv
uv sync --all-extras --group test --group docs --link-mode=copy
uv run pre-commit install
