ARG PYTHON_VERSION=3.12
ARG FINAL_IMAGE=python:${PYTHON_VERSION}-slim

FROM ${FINAL_IMAGE} AS final

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    tini \
    && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip && \
    pip install poetry && \
    poetry config virtualenvs.create false

WORKDIR /src

COPY . ./
RUN poetry install --without dev

ENTRYPOINT ["/usr/bin/tini", "--"]
