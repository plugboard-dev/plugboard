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


@pytest.mark.parametrize(
    "process_type,expected_state_backend",
    [
        ("plugboard.process.RayProcess", RAY_STATE_BACKEND_CLS_PATH),
        ("plugboard.process.LocalProcess", DEFAULT_STATE_BACKEND_CLS_PATH),
    ],
)
def test_process_default_state_backend(process_type: str, expected_state_backend: str) -> None:
    """Tests that each process type defaults to the appropriate state backend."""
    spec_dict = {
        "type": process_type,
        "args": {
            "components": [
                {
                    "type": "tests.integration.test_process_with_components_run.A",
                    "args": {"name": "A", "iters": 1},
                }
            ]
        },
    }
    # Add connector_builder for RayProcess (required)
    if process_type == "plugboard.process.RayProcess":
        spec_dict["connector_builder"] = {"type": "plugboard.connector.RayConnector"}

    spec = ProcessSpec.model_validate(spec_dict)
    assert spec.args.state.type == expected_state_backend


def test_ray_process_explicit_state_backend() -> None:
    """Tests that explicitly set state backend is not overridden for RayProcess."""
    # Test with explicit state backend (not RayStateBackend)
    spec_dict = {
        "type": "plugboard.process.RayProcess",
        "connector_builder": {"type": "plugboard.connector.RayConnector"},
        "args": {
            "components": [
                {
                    "type": "tests.integration.test_process_with_components_run.A",
                    "args": {"name": "A", "iters": 1},
                }
            ],
            "state": {"type": "plugboard.state.SqliteStateBackend"},
        },
    }
    spec = ProcessSpec.model_validate(spec_dict)
    # Must preserve explicitly set state backend
    assert spec.args.state.type == "plugboard.state.SqliteStateBackend"
