"""Integration tests for the `Tuner` class."""

import math
import typing as _t

import msgspec
from optuna import Trial
import pytest

from plugboard.component import IOController as IO
from plugboard.exceptions import ConstraintError
from plugboard.schemas import ConfigSpec, ConnectorBuilderSpec, ObjectiveSpec
from plugboard.schemas.tune import (
    CategoricalParameterSpec,
    IntParameterSpec,
    OptunaSpec,
)
from plugboard.tune import Tuner
from tests.conftest import ComponentTestHelper
from tests.integration.test_process_with_components_run import A, B, C  # noqa: F401


class ConstrainedB(B):
    """Component with a constraint."""

    async def step(self) -> None:
        """Override step to apply a constraint."""
        if self.in_1 > 10:
            raise ConstraintError("Input must not be greater than 10")
        await super().step()


class DynamicListComponent(ComponentTestHelper):
    """Component with a dynamic list parameter for tuning."""

    io = IO(inputs=["in_1"], outputs=["out_1"])

    def __init__(self, list_param: list[float], *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._list_param = list_param

    async def step(self) -> None:
        """Compute output based on dynamic list parameter."""
        self.out_1 = sum(self._list_param) * self.in_1


@pytest.fixture
def config() -> dict:
    """Loads the YAML config."""
    with open("tests/data/minimal-process.yaml", "rb") as f:
        return msgspec.yaml.decode(f.read())


@pytest.fixture
def dynamic_param_config() -> dict:
    """Loads the YAML config with dynamic list included."""
    with open("tests/data/dynamic-param-process.yaml", "rb") as f:
        return msgspec.yaml.decode(f.read())


def custom_space(trial: Trial) -> dict[str, _t.Any] | None:
    """Defines a custom search space for Optuna."""
    n_list = trial.suggest_int("n_list", 1, 10)
    list_param = [
        trial.suggest_float(f"list_param_{i}", -5.0, -5.0 + float(i)) for i in range(n_list)
    ]
    # Set existing parameter
    trial.suggest_int("a.iters", 1, 10)
    # Use the return value to set the list parameter
    return {"d.list_param": list_param}


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
        process_spec.args.state.type = "plugboard.state.RayStateBackend"
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
    assert not any(t.error for t in result)
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
    assert not any(t.error for t in result)
    # Constraint must be respected
    assert all(t.metrics["c.in_1"] <= 10 for t in result)
    # Optimum must be less than or equal to 10
    assert best_result.metrics["c.in_1"] <= 10
    # If a.iters is greater than 11, the constraint will be violated
    assert all(t.metrics["c.in_1"] == -math.inf for t in result if t.config["a.iters"] > 11)


@pytest.mark.tuner
@pytest.mark.asyncio
async def test_custom_space_tune(dynamic_param_config: dict, ray_ctx: None) -> None:
    """Tests tuning with a custom search space."""
    spec = ConfigSpec.model_validate(dynamic_param_config)
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
                lower=1,
                upper=3,
            ),
            CategoricalParameterSpec(
                object_type="component",
                object_name="d",
                field_type="arg",
                field_name="list_param",
                categories=[],  # Will be set by custom space
            ),
        ],
        num_samples=10,
        mode="max",
        max_concurrent=2,
        algorithm=OptunaSpec(space="tests.integration.test_tuner.custom_space"),
    )
    tuner.run(
        spec=process_spec,
    )
    result = tuner.result_grid
    # There must be no failed trials
    assert not any(t.error for t in result)
    # The custom space must have been used
    for r in result:
        # Set the length of the list parameter based on n_list
        assert len(r.config["d.list_param"]) == r.config["n_list"]
        if r.config["n_list"] < 5:
            # When n_list < 5, all list_param values are negative
            assert all(v < 0.0 for v in r.config["d.list_param"])
