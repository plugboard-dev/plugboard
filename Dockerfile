ARG PYTHON_VERSION=3.12
ARG FINAL_IMAGE=python:${PYTHON_VERSION}-slim

FROM ${FINAL_IMAGE} AS final

RUN pip install --upgrade pip && \
    pip install poetry && \
    poetry config --local virtualenvs.create true && \
    poetry config --local virtualenvs.in-project true

WORKDIR /src
COPY . ./
RUN poetry install --without dev

ENTRYPOINT ["/usr/bin/tini", "--"]
