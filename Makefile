SHELL := /bin/bash
PROJECT := plugboard
PYTHON_VERSION ?= 3.12
VENV_NAME := $(PROJECT)-$(PYTHON_VERSION)
WITH_PYENV := $(shell which pyenv > /dev/null && echo true || echo false)
VIRTUAL_ENV ?= $(shell $(WITH_PYENV) && echo $$(pyenv root)/versions/$(VENV_NAME) || echo $(PWD)/.venv)
VENV := $(VIRTUAL_ENV)
SRC := ./plugboard
TESTS := ./tests

# poetry settings
POETRY_VIRTUALENVS_PREFER_ACTIVE_PYTHON := $(shell $(WITH_PYENV) && echo true || echo false)
POETRY_VIRTUALENVS_CREATE := false
POETRY_VIRTUALENVS_IN_PROJECT := true

# Windows compatibility
PYTHON := $(VENV)/bin/python
ifeq ($(OS), Windows_NT)
    PYTHON := $(VENV)/Scripts/python
endif

.PHONY: all
all: lint test

.PHONY: clean
clean:
	$(WITH_PYENV) && pyenv virtualenv-delete -f $(VENV_NAME) || rm -rf $(VENV)
	$(WITH_PYENV) && pyenv local --unset || true
	rm -f poetry.lock
	find $(SRC) -type f -name *.pyc -delete
	find $(SRC) -type d -name __pycache__ -delete

$(VENV):
	$(WITH_PYENV) && pyenv install -s $(PYTHON_VERSION) || true
	$(WITH_PYENV) && pyenv virtualenv $(PYTHON_VERSION) $(VENV_NAME) || python$(PYTHON_VERSION) -m venv $(VENV)
	$(WITH_PYENV) && pyenv local $(VENV_NAME) || true
	@touch $@

$(VENV)/.stamps/init-poetry: $(VENV)
	# How to install poetry for with and without pyenv cases?
	$(PYTHON) -m pip install --upgrade pip setuptools poetry-dynamic-versioning[plugin]
	mkdir -p $(VENV)/.stamps
	@touch $@

$(VENV)/.stamps/install: $(VENV)/.stamps/init-poetry pyproject.toml
	# This fails to install anything with the output: No dependencies to install or update
	# Verbose output shows that poetry uses a cached venv on the first run:
	# Found: /home/csk/.pyenv/versions/plugboard-3.12/bin/python
	# Using virtualenv: /home/csk/.cache/pypoetry/virtualenvs/plugboard-OHr21XxN-py3.12
	# Running poetry install a second time (outside of this makefile rule) then installs the dependencies
	# Found: /home/csk/.pyenv/versions/plugboard-3.12/bin/python
	# Using virtualenv: /home/csk/.pyenv/versions/3.12.6/envs/plugboard-3.12
	env | grep POETRY_ || echo
	# POETRY_VIRTUALENVS_CREATE=$(POETRY_VIRTUALENVS_CREATE) $(PYTHON) -m poetry install -v
	poetry env use $(PYTHON) && poetry install -v
	@touch $@

.PHONY: install
install: $(VENV)/.stamps/install

.PHONY: install2
install2:
	env | grep POETRY_ || echo
	# $(PYTHON) -m poetry install -v
	poetry install -v

.PHONY: init
init: install install2

.PHONY: lint
lint: init
	$(PYTHON) -m ruff check
	$(PYTHON) -m mypy $(SRC)/ --explicit-package-bases
	$(PYTHON) -m mypy $(TESTS)/

.PHONY: test
test: init
	$(PYTHON) -m pytest -rs $(TESTS)/ --ignore=$(TESTS)/smoke

.PHONY: docs
docs: $(VENV)
	$(PYTHON) -m mkdocs build

.PHONY: docs-serve
docs-serve: $(VENV)
	$(PYTHON) -m mkdocs serve

.PHONY: build
build: $(VENV) docs
	$(PYTHON) -m poetry build

GIT_HASH_SHORT ?= $(shell git rev-parse --short HEAD)
GIT_BRANCH ?= $(shell git rev-parse --abbrev-ref HEAD | tr / -)
BUILD_DATE = $(shell date -u -Iseconds)
PACKAGE_VERSION ?= $(shell poetry version -s)
PACKAGE_VERSION_DOCKER_SAFE = $(shell echo $(PACKAGE_VERSION) | tr + .)

DOCKER_FILE ?= Dockerfile
DOCKER_REGISTRY ?= ghcr.io
DOCKER_IMAGE ?= plugboard
DOCKER_REGISTRY_IMAGE=${DOCKER_REGISTRY}/plugboard-dev/${DOCKER_IMAGE}

requirements.txt: $(VENV) pyproject.toml
	$(PYTHON) -m poetry export -f requirements.txt -o requirements.txt --without-hashes
	@touch $@

.PHONY: docker-build
docker-build: ${DOCKER_FILE} requirements.txt
	docker build . \
	  -f ${DOCKER_FILE} \
	  --build-arg semver=$(PACKAGE_VERSION) \
	  --build-arg git_hash_short=$(GIT_HASH_SHORT) \
	  --build-arg git_branch=$(GIT_BRANCH) \
	  --build-arg build_date=$(BUILD_DATE) \
	  -t ${DOCKER_IMAGE}:latest \
	  -t ${DOCKER_IMAGE}:${PACKAGE_VERSION_DOCKER_SAFE} \
	  -t ${DOCKER_IMAGE}:${GIT_HASH_SHORT} \
	  -t ${DOCKER_IMAGE}:${GIT_BRANCH} \
	  -t ${DOCKER_REGISTRY_IMAGE}:${PACKAGE_VERSION_DOCKER_SAFE} \
	  -t ${DOCKER_REGISTRY_IMAGE}:${GIT_HASH_SHORT} \
	  -t ${DOCKER_REGISTRY_IMAGE}:${GIT_BRANCH} \
	  --progress=plain 2>&1 | tee docker-build.log

.PHONY: docker-login
docker-login:
	echo $$GITHUB_ACCESS_TOKEN | docker login -u $$GITHUB_USERNAME --password-stdin ${DOCKER_REGISTRY}

.PHONY: docker-push
docker-push:
	docker push --all-tags ${DOCKER_REGISTRY_IMAGE}
