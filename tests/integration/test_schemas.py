"""Integration tests for loading schemas from a Plugboard YAML config."""
# ruff: noqa: D101,D102,D103

import msgspec
import pytest

from plugboard.schemas import ConfigSpec


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
    assert len(process_spec.args.components or []) == 2
    # Must be one connector defined
    assert len(process_spec.args.connectors or []) == 1
