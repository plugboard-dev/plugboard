"""Provides unit tests for the Tuner class."""

from unittest.mock import MagicMock, patch

import msgspec
import pytest

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


@patch("ray.tune.Tuner")
def test_tuner_with_optuna_storage(mock_tuner_cls: MagicMock, config: dict) -> None:
    """Test the Tuner class with Optuna storage URI."""
    mock_tuner = MagicMock()
    mock_tuner_cls.return_value = mock_tuner

    spec = ConfigSpec.model_validate(config)
    process_spec = spec.plugboard.process

    # Test with storage URI
    optuna_spec = OptunaSpec(
        type="ray.tune.search.optuna.OptunaSearch",
        study_name="test-study",
        storage="sqlite:///test.db",
    )

    tuner = Tuner(
        objective=ObjectiveSpec(
            object_type="component",
            object_name="c",
            field_type="field",
            field_name="in_1",
        ),
        parameters=[
            FloatParameterSpec(
                object_type="component",
                object_name="a",
                field_type="arg",
                field_name="y",
                lower=0.1,
                upper=0.5,
            ),
        ],
        num_samples=6,
        mode="max",
        max_concurrent=2,
        algorithm=optuna_spec,
    )
    tuner.run(spec=process_spec)

    # Must call the Tuner class with objective
    assert callable(mock_tuner_cls.call_args.args[0])
    # Must call the Tuner class with parameter space
    kwargs = mock_tuner_cls.call_args.kwargs
    param_space = kwargs["param_space"]
    assert param_space["a.y"].__class__.__name__ == "Float"
    assert param_space["a.y"].lower == 0.1
    assert param_space["a.y"].upper == 0.5
    # Must call the Tuner class with configuration and correct algorithm
    tune_config = kwargs["tune_config"]
    assert tune_config.num_samples == 6
    # Check searcher attribute as this contains the underlying algorithm with storage converted
    assert tune_config.search_alg.searcher.__class__.__name__ == "OptunaSearch"
    # Must call fit method on the Tuner object
    mock_tuner.fit.assert_called_once()


def test_optuna_storage_uri_conversion() -> None:
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
    )

    # Test the _build_algorithm method with storage URI
    optuna_spec = OptunaSpec(
        type="ray.tune.search.optuna.OptunaSearch",
        study_name="test-study",
        storage="sqlite:///test_conversion.db",
    )

    # This should work without raising AssertionError
    algorithm = tuner._build_algorithm(optuna_spec)

    # Verify the algorithm was created successfully
    import ray.tune.search.optuna

    assert isinstance(algorithm, ray.tune.search.optuna.OptunaSearch)


def test_optuna_storage_without_storage() -> None:
    """Test that Optuna algorithm works without storage (default behavior)."""
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
    )

    # Test the _build_algorithm method without storage
    optuna_spec = OptunaSpec(
        type="ray.tune.search.optuna.OptunaSearch",
        study_name="test-study",
        # Note: no storage specified
    )

    # This should work (existing behavior)
    algorithm = tuner._build_algorithm(optuna_spec)

    # Verify the algorithm was created successfully
    import ray.tune.search.optuna

    assert isinstance(algorithm, ray.tune.search.optuna.OptunaSearch)


def test_optuna_invalid_storage_uri() -> None:
    """Test that invalid storage URIs raise appropriate errors."""
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
    )

    # Test the _build_algorithm method with invalid storage URI
    optuna_spec = OptunaSpec(
        type="ray.tune.search.optuna.OptunaSearch", study_name="test-study", storage="invalid://uri"
    )

    # This should raise a ValueError with helpful message
    with pytest.raises(ValueError, match="Failed to create Optuna storage from URI"):
        tuner._build_algorithm(optuna_spec)
