#!/usr/bin/env bash
git config --global --add safe.directory $(pwd)
poetry config virtualenvs.in-project true
poetry install
poetry run pre-commit install
