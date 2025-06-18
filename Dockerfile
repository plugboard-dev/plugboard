# syntax=docker/dockerfile:1.7

# Base stage with common setup --------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS base
RUN addgroup --system --gid 10000 appuser \
  && adduser --system --uid 10000 --gid 10000 --home /home/appuser appuser
WORKDIR /app
RUN chown appuser:appuser /app


# Builder stage with dependency installation to venv ----------------------------------------------
FROM base AS builder
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="${UV_PROJECT_ENVIRONMENT}/bin:${PATH}"
ENV UV_LINK_MODE=copy
ENV UV_CACHE_DIR=/root/.cache/uv

# Install dependencies with pip and requirements.txt to avoid potential cache invalidation
RUN --mount=from=ghcr.io/astral-sh/uv,source=/uv,target=/bin/uv \
  --mount=type=cache,target=/root/.cache/uv \
  --mount=type=bind,source=requirements.txt,target=requirements.txt \
  uv venv ${UV_PROJECT_ENVIRONMENT} && \
  uv pip install -r requirements.txt hatchling


# Final stage with production setup ---------------------------------------------------------------
FROM base AS prod
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="${UV_PROJECT_ENVIRONMENT}/bin:${PATH}"
ENV UV_LINK_MODE=copy
ENV UV_CACHE_DIR=/root/.cache/uv

# Ensure PATH with venv is set in user's bash profile for login shells (required for running in kuberay)
RUN echo "export PATH=${UV_PROJECT_ENVIRONMENT}/bin:\$PATH" >> /home/appuser/.profile && \
    chown appuser:appuser /home/appuser/.profile

# Install required system dependencies for running in kuberay
RUN --mount=type=cache,id=apt,target=/var/cache/apt \
  apt update && apt install -y --no-install-recommends wget

COPY --from=builder ${UV_PROJECT_ENVIRONMENT} ${UV_PROJECT_ENVIRONMENT}

# Install package with version string passed as build arg
ARG semver
ENV SETUPTOOLS_SCM_PRETEND_VERSION=${semver}
RUN --mount=from=ghcr.io/astral-sh/uv,source=/uv,target=/bin/uv \
  --mount=type=bind,target=/app,rw \
  --mount=type=tmpfs,target=/tmp/build \
  --mount=type=cache,target=/root/.cache/uv \
  uv run hatch build -t wheel /tmp/build/dist && \
  uv pip install --no-deps /tmp/build/dist/*.whl

# Get security updates. Relies on cache bust from previous steps.
RUN --mount=type=cache,id=apt,target=/var/cache/apt \
  rm -f /etc/apt/apt.conf.d/docker-clean && \
  apt update && apt upgrade -y && \
  apt autoremove -y && apt clean && rm -rf /var/lib/apt/lists/*

USER appuser

# Git metadata for image identification
ARG git_hash_short
ARG git_branch
ARG build_date
ENV SEMVER=${semver}
ENV GIT_HASH_SHORT=${git_hash_short}
ENV GIT_BRANCH=${git_branch}
ENV BUILD_DATE=${build_date}

CMD python -c "from plugboard import __version__; print('plugboard version', __version__);"
