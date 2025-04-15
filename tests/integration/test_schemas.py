"""Integration tests for loading schemas from a Plugboard YAML config."""
# ruff: noqa: D101,D102,D103

import typing as _t

import msgspec
import pytest

from plugboard.schemas import ConfigSpec
from plugboard.schemas.connector import (
    DEFAULT_CONNECTOR_CLS_PATH,
)


@pytest.fixture
def config() -> dict:
    """Loads the YAML config."""
    with open("tests/data/minimal-process.yaml", "rb") as f:
        return msgspec.yaml.decode(f.read())


def test_load(config: dict) -> None:
    """Tests loading the YAML config."""
    spec = ConfigSpec.model_validate(config)
    process_spec = spec.plugboard.process
    # Must be two components defined
    assert len(process_spec.args.components) == 2
    # Must be one connector defined
    assert len(process_spec.args.connectors) == 1
    # Must default to AsyncioChannelBuilder
    assert process_spec.connector_builder.type == DEFAULT_CONNECTOR_CLS_PATH


@pytest.mark.parametrize(
    "location, value",
    [
        ("plugboard.process.args.components.c.args.path", "new_path"),
        ("plugboard.process.args.connectors.c.name", "new_name"),
        ("plugboard.process.connector_builder.type", "new_type"),
    ],
)
def test_override(config: dict, location: str, value: _t.Any) -> None:
    # spec = ConfigSpec.model_validate(config)

    pass
