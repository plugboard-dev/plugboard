"""Integration tests for the `Tuner` class."""

import math

import msgspec
import pytest

from plugboard.exceptions import ConstraintError
from plugboard.schemas import ConfigSpec, ConnectorBuilderSpec, ObjectiveSpec
from plugboard.schemas.tune import CategoricalParameterSpec, IntParameterSpec, OptunaSpec
from plugboard.tune import Tuner
from tests.integration.test_process_with_components_run import A, B, C  # noqa: F401


class ConstrainedB(B):
    """Component with a constraint."""

    async def step(self) -> None:
        """Override step to apply a constraint."""
        if self.in_1 > 10:
            raise ConstraintError("Input must not be greater than 10")
        await super().step()


@pytest.fixture
def config() -> dict:
    """Loads the YAML config."""
    with open("tests/data/minimal-process.yaml", "rb") as f:
        return msgspec.yaml.decode(f.read())


@pytest.mark.tuner
@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["min", "max"])
@pytest.mark.parametrize("process_type", ["local", "ray"])
async def test_tune(config: dict, mode: str, process_type: str, ray_ctx: None) -> None:
    """Tests running of optimisation jobs."""
    spec = ConfigSpec.model_validate(config)
    process_spec = spec.plugboard.process
    if process_type == "ray":
        process_spec.connector_builder = ConnectorBuilderSpec(
            type="plugboard.connector.RayConnector"
        )
        process_spec.type = "plugboard.process.RayProcess"
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
                lower=6,
                upper=9,
            )
        ],
        num_samples=5,
        mode=mode,
        max_concurrent=2,
        algorithm=OptunaSpec(),
    )
    best_result = tuner.run(
        spec=process_spec,
    )
    result = tuner.result_grid
    # There must be no failed trials
    assert not [t for t in result if t.error]
    # Correct optimimum must be found (within tolerance)
    if mode == "min":
        assert best_result.config["a.iters"] <= tuner._parameters["a.iters"].lower + 2
        assert best_result.metrics["c.in_1"] == best_result.config["a.iters"] - 1
    else:
        assert best_result.config["a.iters"] >= tuner._parameters["a.iters"].upper - 2
        assert best_result.metrics["c.in_1"] == best_result.config["a.iters"] - 1


@pytest.mark.tuner
@pytest.mark.asyncio
async def test_multi_objective_tune(config: dict, ray_ctx: None) -> None:
    """Tests multi-objective optimisation."""
    spec = ConfigSpec.model_validate(config)
    process_spec = spec.plugboard.process
    tuner = Tuner(
        objective=[
            ObjectiveSpec(
                object_type="component",
                object_name="c",
                field_type="field",
                field_name="in_1",
            ),
            ObjectiveSpec(
                object_type="component",
                object_name="b",
                field_type="field",
                field_name="out_1",
            ),
        ],
        parameters=[
            IntParameterSpec(
                object_type="component",
                object_name="a",
                field_type="arg",
                field_name="iters",
                lower=1,
                upper=3,
            ),
            CategoricalParameterSpec(
                object_type="component",
                object_name="b",
                field_type="arg",
                field_name="factor",
                categories=[1, -1],
            ),
        ],
        num_samples=10,
        mode=["max", "min"],
        max_concurrent=2,
    )
    best_result = tuner.run(
        spec=process_spec,
    )
    result = tuner.result_grid
    # There must be no failed trials
    assert not [t for t in result if t.error]
    # Results must contain two objectives and correct optimimum must be found
    # The best result must be a list of two results
    assert len(best_result) == 2
    assert all(r.config["a.iters"] == 2 for r in best_result)
    assert -1 in set(r.config["b.factor"] for r in best_result)
    assert -1 in set(r.metrics["b.out_1"] for r in best_result)
    assert 1 in set(r.metrics["c.in_1"] for r in best_result)


@pytest.mark.tuner
@pytest.mark.asyncio
async def test_tune_with_constraint(config: dict, ray_ctx: None) -> None:
    """Tests running of optimisation jobs with a constraint."""
    spec = ConfigSpec.model_validate(config)
    process_spec = spec.plugboard.process
    # Replace component B with a constrained version
    process_spec.args.components[1].type = "tests.integration.test_tuner.ConstrainedB"
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
                upper=15,
            )
        ],
        num_samples=12,
        mode="max",
        max_concurrent=2,
        algorithm=OptunaSpec(),
    )
    best_result = tuner.run(
        spec=process_spec,
    )
    result = tuner.result_grid
    # There must be no failed trials
    assert not [t for t in result if t.error]
    # Constraint must be respected
    assert all(t.metrics["c.in_1"] <= 10 for t in result)
    # Optimum must be less than or equal to 10
    assert best_result.metrics["c.in_1"] <= 10
    # If a.iters is greater than 11, the constraint will be violated
    assert all(t.metrics["c.in_1"] == -math.inf for t in result if t.config["a.iters"] > 11)
