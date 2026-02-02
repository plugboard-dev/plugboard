"""Integration tests for loading schemas from a Plugboard YAML config."""
# ruff: noqa: D101,D102,D103

import msgspec
import pytest

from plugboard.schemas import (
    DEFAULT_CONNECTOR_CLS_PATH,
    DEFAULT_STATE_BACKEND_CLS_PATH,
    RAY_STATE_BACKEND_CLS_PATH,
    ConfigSpec,
    ProcessSpec,
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
    assert len(process_spec.args.components) == 3
    # Must be one connector defined
    assert len(process_spec.args.connectors) == 2
    # Must default to AsyncioChannelBuilder
    assert process_spec.connector_builder.type == DEFAULT_CONNECTOR_CLS_PATH


def test_ray_process_default_state_backend() -> None:
    """Tests that RayProcess defaults to RayStateBackend when state not explicitly set."""
    # Test with minimal RayProcess spec - no explicit state
    spec_dict = {
        "type": "plugboard.process.RayProcess",
        "connector_builder": {"type": "plugboard.connector.RayConnector"},
        "args": {
            "components": [
                {"type": "tests.integration.test_process_with_components_run.A", "args": {"name": "A", "iters": 1}}
            ]
        }
    }
    spec = ProcessSpec.model_validate(spec_dict)
    # Must default to RayStateBackend for RayProcess
    assert spec.args.state.type == RAY_STATE_BACKEND_CLS_PATH


def test_local_process_default_state_backend() -> None:
    """Tests that LocalProcess defaults to DictStateBackend when state not explicitly set."""
    # Test with minimal LocalProcess spec - no explicit state
    spec_dict = {
        "type": "plugboard.process.LocalProcess",
        "args": {
            "components": [
                {"type": "tests.integration.test_process_with_components_run.A", "args": {"name": "A", "iters": 1}}
            ]
        }
    }
    spec = ProcessSpec.model_validate(spec_dict)
    # Must default to DictStateBackend for LocalProcess
    assert spec.args.state.type == DEFAULT_STATE_BACKEND_CLS_PATH


def test_ray_process_explicit_state_backend() -> None:
    """Tests that explicitly set state backend is not overridden for RayProcess."""
    # Test with explicit state backend (not RayStateBackend)
    spec_dict = {
        "type": "plugboard.process.RayProcess",
        "connector_builder": {"type": "plugboard.connector.RayConnector"},
        "args": {
            "components": [
                {"type": "tests.integration.test_process_with_components_run.A", "args": {"name": "A", "iters": 1}}
            ],
            "state": {"type": "plugboard.state.SqliteStateBackend"}
        }
    }
    spec = ProcessSpec.model_validate(spec_dict)
    # Must preserve explicitly set state backend
    assert spec.args.state.type == "plugboard.state.SqliteStateBackend"
