SHELL := /bin/bash
PROJECT := plugboard
PYTHON_VERSION ?= 3.12
PY := python$(PYTHON_VERSION)
WITH_PYENV := $(shell which pyenv > /dev/null && echo true || echo false)
VIRTUAL_ENV ?= $(shell $(WITH_PYENV) && echo $(shell pyenv root)/versions/$(PROJECT) || echo $(PWD)/.venv)
VENV := $(VIRTUAL_ENV)
BIN := $(VENV)/bin
SRC := ./plugboard
TESTS := ./tests

# Windows compatibility
ifeq ($(OS), Windows_NT)
    BIN := $(VENV)/Scripts
    PY := python
endif

.PHONY: all
all: lint test

.PHONY: clean
clean:
	$(WITH_PYENV) && pyenv virtualenv-delete -f $(PROJECT) || rm -rf $(VENV)
	find $(SRC) -type f -name *.pyc -delete
	find $(SRC) -type d -name __pycache__ -delete

$(VENV):
	$(WITH_PYENV) && pyenv virtualenv $(PYTHON_VERSION) $(PROJECT) || $(PY) -m venv $(VENV)
	@touch $@

$(VENV)/.stamps/init-poetry: $(VENV)
	$(BIN)/$(PY) -m pip install --upgrade pip setuptools poetry poetry-dynamic-versioning[plugin]
	$(BIN)/$(PY) -m poetry config virtualenvs.in-project true
	$(BIN)/$(PY) -m poetry config virtualenvs.prompt venv
	mkdir -p $(VENV)/.stamps
	@touch $@

$(VENV)/.stamps/install: pyproject.toml
	$(BIN)/$(PY) -m poetry install
	@touch $@

.PHONY: install
install: $(VENV)/.stamps/install

.PHONY: init
init: $(VENV)/.stamps/init-poetry install

.PHONY: lint
lint: init
	$(BIN)/$(PY) -m ruff check
	$(BIN)/$(PY) -m mypy $(SRC)/ --explicit-package-bases
	$(BIN)/$(PY) -m mypy $(TESTS)/

.PHONY: test
test: init
	$(BIN)/$(PY) -m pytest -rs $(TESTS)/ --ignore=$(TESTS)/smoke

.PHONY: docs
docs: $(VENV)
	$(BIN)/$(PY) -m mkdocs build

.PHONY: docs-serve
docs-serve: $(VENV)
	$(BIN)/$(PY) -m mkdocs serve

.PHONY: build
build: $(VENV) docs
	$(BIN)/$(PY) -m poetry build

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
	$(BIN)/$(PY) -m poetry export -f requirements.txt -o requirements.txt --without-hashes
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
