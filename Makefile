SHELL := /bin/bash
VENV := .venv
BIN := $(VENV)/bin
PYTHON_VERSION ?= 3.12
PY := python$(PYTHON_VERSION)
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
	rm -rf $(VENV)
	find $(SRC) -type f -name *.pyc -delete
	find $(SRC) -type d -name __pycache__ -delete

$(VENV):
	$(PY) -m venv $(VENV)
	$(BIN)/$(PY) -m pip install --upgrade pip setuptools poetry poetry-dynamic-versioning[plugin]
	$(BIN)/$(PY) -m poetry config virtualenvs.in-project true
	$(BIN)/$(PY) -m poetry config virtualenvs.prompt venv
	mkdir -p $(VENV)/.stamps
	@touch $@

$(VENV)/.stamps/init: $(VENV) pyproject.toml
	$(BIN)/$(PY) -m poetry install
	@touch $@

.PHONY: init
init: $(VENV)/.stamps/init

.PHONY: lint
lint: init
	$(BIN)/$(PY) -m ruff check
	$(BIN)/$(PY) -m mypy $(SRC)/ --explicit-package-bases
	$(BIN)/$(PY) -m mypy $(TESTS)/

.PHONY: test
test: init
	$(BIN)/$(PY) -m pytest -rs $(TESTS)/ --ignore=$(TESTS)/smoke

.PHONY: build
build: $(VENV)
	$(BIN)/$(PY) -m poetry build

GIT_HASH_SHORT ?= $(shell git rev-parse --short HEAD)
GIT_BRANCH ?= $(shell git rev-parse --abbrev-ref HEAD | tr / -)
BUILD_DATE = $(shell date -u -Iseconds)
PACKAGE_VERSION ?= $(shell poetry version -s)
PACKAGE_VERSION_DOCKER_SAFE = $(shell echo $(PACKAGE_VERSION) | tr + .)

DOCKER_FILE ?= Dockerfile
DOCKER_REGISTRY ?= ghcr.io
DOCKER_IMAGE ?= plugboard

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
	  -t ${DOCKER_REGISTRY}/${DOCKER_IMAGE}:${PACKAGE_VERSION_DOCKER_SAFE} \
	  -t ${DOCKER_REGISTRY}/${DOCKER_IMAGE}:${GIT_HASH_SHORT} \
	  -t ${DOCKER_REGISTRY}/${DOCKER_IMAGE}:${GIT_BRANCH} \
	  --progress=plain 2>&1 | tee docker-build.log

.PHONY: docker-push
docker-push:
	docker push --all-tags ${DOCKER_REGISTRY}/${DOCKER_IMAGE}
