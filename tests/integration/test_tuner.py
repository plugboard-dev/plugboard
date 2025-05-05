"""Integration tests for the `Tuner` class."""

import msgspec
import pytest

from plugboard.schemas import ConfigSpec, ObjectiveSpec
from plugboard.schemas.tune import IntParameterSpec
from plugboard.tune import Tuner


@pytest.fixture
def config() -> dict:
    """Loads the YAML config."""
    with open("tests/data/minimal-process.yaml", "rb") as f:
        return msgspec.yaml.decode(f.read())


def test_tune(config: dict) -> None:
    """Tests running of optimisation jobs."""
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
                field_name="iters",
                lower=5,
                upper=10,
            )
        ],
        num_samples=10,
        mode="max",
    )
    result = tuner.run(
        spec=process_spec,
    )
    # There must be no failed trials
    assert not [t for t in result if t.error]
