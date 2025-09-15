"""Provides unit tests for the Tuner class."""

from tempfile import TemporaryDirectory
import typing as _t
from unittest.mock import MagicMock, patch

import msgspec
import pytest
import ray.tune

from plugboard.schemas import ConfigSpec, ObjectiveSpec
from plugboard.schemas.tune import (
    CategoricalParameterSpec,
    FloatParameterSpec,
    IntParameterSpec,
    OptunaSpec,
)
from plugboard.tune import Tuner
from tests.integration.test_process_with_components_run import A, B, C  # noqa: F401


@pytest.fixture
def config() -> dict:
    """Loads the YAML config."""
    with open("tests/data/minimal-process.yaml", "rb") as f:
        return msgspec.yaml.decode(f.read())


@pytest.fixture
def temp_dir() -> _t.Iterator[str]:
    """Creates a temporary directory."""
    with TemporaryDirectory() as tmpdir:
        yield tmpdir


@patch("ray.tune.Tuner")
def test_tuner(mock_tuner_cls: MagicMock, config: dict) -> None:
    """Test the Tuner class."""
    mock_tuner = MagicMock()
    mock_tuner_cls.return_value = mock_tuner

    spec = ConfigSpec.model_validate(config)
    process_spec = spec.plugboard.process
    tuner = Tuner(
        objective=ObjectiveSpec(
            object_type="component",
            object_name="c",
            field_type="field",
            field_name="in_1",
        ),
        parameters=[
            IntParameterSpec(
                object_type="component",
                object_name="a",
                field_type="arg",
                field_name="x",
                lower=6,
                upper=8,
            ),
            FloatParameterSpec(
                object_type="component",
                object_name="a",
                field_type="arg",
                field_name="y",
                lower=0.1,
                upper=0.5,
            ),
            CategoricalParameterSpec(
                object_type="component",
                object_name="b",
                field_type="arg",
                field_name="z",
                categories=["a", "b", "c"],
            ),
        ],
        num_samples=6,
        mode="max",
        max_concurrent=2,
    )
    tuner.run(spec=process_spec)

    # Must call the Tuner class with objective
    assert callable(mock_tuner_cls.call_args.args[0])
    # Must call the Tuner class with parameter space
    kwargs = mock_tuner_cls.call_args.kwargs
    param_space = kwargs["param_space"]
    assert param_space["a.x"].__class__.__name__ == "Integer"
    assert param_space["a.x"].lower == 6
    assert param_space["a.x"].upper == 8
    assert param_space["a.y"].__class__.__name__ == "Float"
    assert param_space["a.y"].lower == 0.1
    assert param_space["a.y"].upper == 0.5
    assert param_space["b.z"].__class__.__name__ == "Categorical"
    assert param_space["b.z"].categories == ["a", "b", "c"]
    # Must call the Tuner class with configuration and correct algorithm
    tune_config = kwargs["tune_config"]
    assert tune_config.num_samples == 6
    # Check searcher attribute as this contains the underlying algorithm
    assert tune_config.search_alg.searcher.__class__.__name__ == "OptunaSearch"
    # Must call fit method on the Tuner object
    mock_tuner.fit.assert_called_once()


def test_optuna_storage_uri_conversion(temp_dir: str) -> None:
    """Test that storage URI gets converted to Optuna storage object."""
    # Create a tuner with minimal configuration
    tuner = Tuner(
        objective=ObjectiveSpec(
            object_type="component", object_name="test", field_type="field", field_name="value"
        ),
        parameters=[
            FloatParameterSpec(
                object_type="component",
                object_name="test",
                field_type="arg",
                field_name="param",
                lower=0.0,
                upper=1.0,
            )
        ],
        num_samples=1,
        mode="max",
        algorithm=OptunaSpec(
            type="ray.tune.search.optuna.OptunaSearch",
            study_name="test-study",
            storage=f"sqlite:///{temp_dir}/test_conversion.db",
        ),
    )
    algo = tuner._config.search_alg
    assert isinstance(algo, ray.tune.search.optuna.OptunaSearch)
