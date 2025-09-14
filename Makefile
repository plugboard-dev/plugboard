SHELL := /bin/bash
VENV := .venv
PROJECT := plugboard
PYTHON_VERSION ?= 3.13
PY := python$(PYTHON_VERSION)
SRC := ./plugboard
TESTS := ./tests
# Windows compatibility
ifeq ($(OS), Windows_NT)
    PY := python
endif

.PHONY: all
all: lint test

.PHONY: clean
clean:
	rm -rf $(VENV)
	rm -f uv.lock
	find $(SRC) -type f -name *.pyc -delete
	find $(SRC) -type d -name __pycache__ -delete

$(VENV):
	uv venv ${VENV} --python $(PY)
	@touch $@

$(VENV)/__makefile_stamps_init: $(VENV) pyproject.toml
	uv sync --all-extras --all-groups
	@touch $@

.PHONY: init
init: $(VENV)/__makefile_stamps_init

.PHONY: lint
lint: init
	uv run ruff check
	uv run ruff format --check
	uv run mypy $(SRC)/ --explicit-package-bases
	uv run mypy $(TESTS)/

.PHONY: test
test: init
	uv run pytest -rs $(TESTS)/ --ignore=$(TESTS)/smoke

.PHONY: build
build: $(VENV)
	uv build

.PHONY: docs
docs: $(VENV)
	uv run -m mkdocs build

MKDOCS_PORT ?= 8000
.PHONY: docs-serve
docs-serve: $(VENV) docs
	uv run -m mkdocs serve -a localhost:$(MKDOCS_PORT)

GIT_HASH_SHORT ?= $(shell git rev-parse --short HEAD)
GIT_BRANCH ?= $(shell git rev-parse --abbrev-ref HEAD | tr / -)
BUILD_DATE = $(shell date -u -Iseconds)
PACKAGE_VERSION ?= $(shell uv run hatch version)
PACKAGE_VERSION_DOCKER_SAFE = $(shell echo $(PACKAGE_VERSION) | tr + .)

DOCKER_FILE ?= Dockerfile
DOCKER_REGISTRY ?= ghcr.io
DOCKER_IMAGE ?= plugboard
DOCKER_REGISTRY_IMAGE=${DOCKER_REGISTRY}/plugboard-dev/${DOCKER_IMAGE}

requirements.txt: $(VENV) pyproject.toml
	uv export --all-extras --format requirements-txt --no-hashes --no-editable --no-dev --no-emit-project > requirements.txt
	@touch $@

.PHONY: docker-build
docker-build: ${DOCKER_FILE} requirements.txt
	docker buildx build . \
	  -f ${DOCKER_FILE} \
  	  --provenance=false \
	  --cache-from ${DOCKER_IMAGE}:latest \
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
	  --progress=plain

.PHONY: docker-login
docker-login:
	echo $$GITHUB_ACCESS_TOKEN | docker login -u $$GITHUB_USERNAME --password-stdin ${DOCKER_REGISTRY}

.PHONY: docker-push
docker-push:
	docker push --all-tags ${DOCKER_REGISTRY_IMAGE}
