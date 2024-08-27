#!/usr/bin/env bash
pipx install poetry
poetry config virtualenvs.prefer-active-python true
poetry install
