# syntax=docker/dockerfile:1.7

# Base stage with common setup --------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS base
RUN addgroup --system --gid 10000 appuser \
  && adduser --system --uid 10000 --gid 10000 --home /home/appuser appuser
WORKDIR /app
RUN chown appuser:appuser /app


# Builder stage with dependency installation to venv ----------------------------------------------
FROM base AS builder
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"
ENV PIP_CACHE_DIR=/root/.cache/pip
RUN python -m venv ${VIRTUAL_ENV}

# Install poetry into venv
RUN --mount=type=cache,id=pip,target=/root/.cache/pip \
  pip install poetry==1.8.2 poetry-dynamic-versioning[plugin]==1.2.0

# Install dependencies with pip to avoid potential cache invalidation due to extra poetry package metadata
COPY requirements.txt ./
RUN --mount=type=cache,id=pip,target=/root/.cache/pip \
  pip install -r requirements.txt


# Final stage with production setup ---------------------------------------------------------------
FROM base AS prod
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

# Install package with version string passed as build arg
ARG package_version
ENV POETRY_DYNAMIC_VERSIONING_BYPASS=${package_version}
RUN --mount=type=bind,target=/app,rw --mount=type=tmpfs,target=/tmp/build \
  poetry build -f wheel -o /tmp/build/dist && \
  pip install --no-deps /tmp/build/dist/*.whl

# Get security updates. Relies on cache bust from previous steps.
RUN --mount=type=cache,id=apt,target=/var/cache/apt \
  rm -f /etc/apt/apt.conf.d/docker-clean && \
  apt update && apt upgrade -y && \
  apt autoremove -y && apt clean && rm -rf /var/lib/apt/lists/*

USER appuser

# Git metadata for image identification
ARG git_hash_short
ARG git_branch
ARG git_tag
ARG build_date
ENV GIT_HASH_SHORT=${git_hash_short}
ENV GIT_BRANCH=${git_branch}
ENV GIT_TAG=${git_tag}
ENV BUILD_DATE=${build_date}

CMD python -c "from plugboard import __version__; print(__version__);"
