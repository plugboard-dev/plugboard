"""Provides unit tests for the schemas module."""

import msgspec
import pytest

from plugboard.schemas import ConfigSpec, TuneArgsSpec, TuneSpec


def test_config_spec() -> None:
    """Tests loading the `ConfigSpec` schema."""
    with open("tests/data/minimal-process.yaml", "rb") as f:
        config_minimal = msgspec.yaml.decode(f.read())
    # Validate the ConfigSpec with the loaded configuration
    minimal = ConfigSpec.model_validate(config_minimal)

    with open("tests/data/minimal-process-with-tune.yaml", "rb") as f:
        config_tune = msgspec.yaml.decode(f.read())
    # Validate the ConfigSpec with the configuration containing TuneSpec
    with_tune = ConfigSpec.model_validate(config_tune)

    # ProcessSpec should be present in both configurations
    assert minimal.plugboard.process == with_tune.plugboard.process


def test_tune_spec() -> None:
    """Test the TuneSpec class."""
    valid_spec = {
        "objective": {
            "object_type": "component",
            "object_name": "my_component",
            "field_name": "my_metric",
        },
        "parameters": [
            {
                "object_type": "component",
                "object_name": "my_component",
                "field_type": "arg",
                "field_name": "my_param",
                "type": "ray.tune.uniform",
                "lower": 0.0,
                "upper": 1.0,
            },
            {
                "object_type": "component",
                "object_name": "my_component",
                "field_type": "initial_value",
                "field_name": "x",
                "type": "ray.tune.randint",
                "lower": 1,
                "upper": 10,
            },
            {
                "object_type": "component",
                "object_name": "my_component",
                "field_type": "arg",
                "field_name": "my_choice",
                "categories": ["option1", "option2", "option3"],
            },
        ],
        "num_samples": 100,
        "mode": "max",
        "max_concurrent": 5,
        "algorithm": {
            "type": "ray.tune.search.optuna.OptunaSearch",
            "study_name": "my_study",
            "storage": "sqlite:///my_study.db",
        },
    }
    # Validate the TuneSpec with the valid specification
    _ = TuneSpec(args=TuneArgsSpec.model_validate(valid_spec))

    invalid_spec = valid_spec.copy()
    invalid_spec["mode"] = ["min", "max"]
    # Invalid mode should raise a validation error
    with pytest.raises(ValueError):
        _ = TuneSpec(args=TuneArgsSpec.model_validate(invalid_spec))

    invalid_spec["objective"] = [
        {
            "object_type": "component",
            "object_name": "my_component",
            "field_name": "my_metric",
        },
        {
            "object_type": "component",
            "object_name": "another_component",
            "field_name": "another_metric",
        },
        {
            "object_type": "component",
            "object_name": "my_component",
            "field_name": "yet_another_metric",
        },
    ]
    # Invalid objective length should raise a validation error
    with pytest.raises(ValueError):
        _ = TuneSpec(args=TuneArgsSpec.model_validate(invalid_spec))
