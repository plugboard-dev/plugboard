SHELL := /bin/bash
PROJECT := plugboard
PYTHON_VERSION ?= 3.12
WITH_PYENV := $(shell which pyenv > /dev/null && echo true || echo false)
VENV_NAME := $(PROJECT)-$(PYTHON_VERSION)
VIRTUAL_ENV ?= $(shell $(WITH_PYENV) && echo $(shell pyenv root)/versions/$(VENV_NAME) || echo $(PWD)/.venv)
VENV := $(VIRTUAL_ENV)
SRC := ./plugboard
TESTS := ./tests

PYTHON := $(VENV)/bin/python
# Windows compatibility
ifeq ($(OS), Windows_NT)
    PYTHON := $(VENV)/Scripts/python
endif

.EXPORT_ALL_VARIABLES:
VIRTUAL_ENV = $(VENV)
PATH = $(VENV)/bin:$(shell echo $$PATH)
POETRY_VIRTUALENVS_PREFER_ACTIVE_PYTHON = true
POETRY_VIRTUALENVS_CREATE = false
POETRY_VIRTUALENVS_IN_PROJECT = true

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
	$(PYTHON) -m pip install --upgrade pip setuptools poetry poetry-dynamic-versioning[plugin]
	@mkdir -p $(VENV)/.stamps
	@touch $@

$(VENV)/.stamps/install: $(VENV)/.stamps/init-poetry pyproject.toml
	$(PYTHON) -m poetry install --with docs
	@mkdir -p $(VENV)/.stamps
	@touch $@

.PHONY: install
install: $(VENV)/.stamps/install

.PHONY: init
init: install

.PHONY: lint
lint: init
	$(PYTHON) -m ruff check
	$(PYTHON) -m ruff format --check
	$(PYTHON) -m mypy $(SRC)/ --explicit-package-bases
	$(PYTHON) -m mypy $(TESTS)/

.PHONY: test
test: init
	$(PYTHON) -m pytest -rs $(TESTS)/ --ignore=$(TESTS)/smoke

.PHONY: docs
docs: $(VENV)
	$(PYTHON) -m mkdocs build

MKDOCS_PORT ?= 8000
.PHONY: docs-serve
docs-serve: $(VENV) docs
	$(PYTHON) -m mkdocs serve -a localhost:$(MKDOCS_PORT)

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
