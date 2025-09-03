"""Provides `Tuner` class for optimising Plugboard processes."""

from inspect import isfunction
import math
from pydoc import locate
import typing as _t

import ray.tune.search.optuna

from plugboard.component.component import Component, ComponentRegistry
from plugboard.exceptions import ConstraintError
from plugboard.process import Process, ProcessBuilder
from plugboard.schemas import (
    Direction,
    ObjectiveSpec,
    OptunaSpec,
    ParameterSpec,
    ProcessSpec,
)
from plugboard.utils import DI, run_coro_sync
from plugboard.utils.dependencies import depends_on_optional


try:
    import optuna.storages
    import ray.tune
    import ray.tune.search
except ImportError:  # pragma: no cover
    pass


class Tuner:
    """A class for running optimisation on Plugboard processes."""

    @depends_on_optional("ray")
    def __init__(
        self,
        *,
        objective: ObjectiveSpec | list[ObjectiveSpec],
        parameters: list[ParameterSpec],
        num_samples: int,
        mode: Direction | list[Direction] = "max",
        max_concurrent: _t.Optional[int] = None,
        algorithm: _t.Optional[OptunaSpec] = None,
    ) -> None:
        """Instantiates the `Tuner` class.

        Args:
            objective: The objective(s) to optimise for in the `Process`.
            parameters: The parameters to optimise over.
            num_samples: The number of trial samples to use for the optimisation.
            mode: The direction of the optimisation.
            max_concurrent: The maximum number of concurrent trials. Defaults to None, which means
                that Ray will use its default concurrency of 1 trial per CPU core.
            algorithm: Configuration for the underlying Optuna algorithm used for optimisation.
        """
        self._logger = DI.logger.resolve_sync().bind(cls=self.__class__.__name__)
        # Check that objective and mode are lists of the same length if multiple objectives are used
        self._check_objective(objective, mode)
        self._objective = objective if isinstance(objective, list) else [objective]
        self._mode = [str(m) for m in mode] if isinstance(mode, list) else str(mode)
        self._metric = (
            [obj.full_name for obj in self._objective]
            if len(self._objective) > 1
            else self._objective[0].full_name
        )

        self._parameters_dict = {p.full_name: p for p in parameters}
        self._parameters = dict(self._build_parameter(p) for p in parameters)
        _algo = self._build_algorithm(algorithm)
        if max_concurrent is not None:
            _algo = ray.tune.search.ConcurrencyLimiter(_algo, max_concurrent)
        self._config = ray.tune.TuneConfig(
            num_samples=num_samples,
            search_alg=_algo,
        )
        self._result_grid: _t.Optional[ray.tune.ResultGrid] = None
        self._logger.info("Tuner created")

    @property
    def result_grid(self) -> ray.tune.ResultGrid:
        """Returns a [`ResultGrid`][ray.tune.ResultGrid] summarising the optimisation results."""
        if self._result_grid is None:
            raise ValueError("No result grid available. Run the optimisation job first.")
        return self._result_grid

    @classmethod
    def _check_objective(
        cls, objective: ObjectiveSpec | list[ObjectiveSpec], mode: Direction | list[Direction]
    ) -> None:
        """Check that the objective and mode are valid."""
        if isinstance(objective, list):
            if not isinstance(mode, list):
                raise ValueError("If using multiple objectives, `mode` must also be a list.")
            if len(objective) != len(mode):
                raise ValueError(
                    "If using multiple objectives, `mode` and `objective` must be the same length."
                )
        else:
            if isinstance(mode, list):
                raise ValueError("If using a single objective, `mode` must not be a list.")

    def _build_algorithm(
        self, algorithm: _t.Optional[OptunaSpec] = None
    ) -> ray.tune.search.Searcher:
        if algorithm is None:
            self._logger.info("Using default Optuna search algorithm")
            return ray.tune.search.optuna.OptunaSearch(metric=self._metric, mode=self._mode)
        _algo_kwargs = {
            **algorithm.model_dump(exclude={"type"}),
            "mode": self._mode,
            "metric": self._metric,
        }

        # Convert storage URI string to optuna storage object if needed
        # TODO: Make this more general to support other algorithms, e.g. use a builder class
        if "storage" in _algo_kwargs and isinstance(_algo_kwargs["storage"], str):
            _algo_kwargs["storage"] = optuna.storages.RDBStorage(url=_algo_kwargs["storage"])
            self._logger.info(
                "Converted storage URI to Optuna RDBStorage object",
                storage_uri=algorithm.storage,
            )

        algo_cls: _t.Optional[_t.Any] = locate(algorithm.type)
        if not algo_cls or not issubclass(algo_cls, ray.tune.search.searcher.Searcher):
            raise ValueError(f"Could not locate `Searcher` class {algorithm.type}")
        self._logger.info(
            "Using custom search algorithm",
            algorithm=algorithm.type,
            params={
                k: v if k != "storage" else f"<{type(v).__name__}>" for k, v in _algo_kwargs.items()
            },
        )
        return algo_cls(**_algo_kwargs)

    def _build_parameter(
        self, parameter: ParameterSpec
    ) -> tuple[str, ray.tune.search.sample.Sampler]:
        parameter_cls: _t.Optional[_t.Any] = locate(parameter.type)
        if not parameter_cls or not isfunction(parameter_cls):
            raise ValueError(f"Could not locate parameter class {parameter.type}")
        return parameter.full_name, parameter_cls(
            # The schema will exclude the object and field names and types
            **parameter.model_dump(exclude={"type"})
        )

    @staticmethod
    def _override_parameter(
        process: ProcessSpec, param: ParameterSpec, value: _t.Any
    ) -> None:  # pragma: no cover
        if param.object_type != "component":
            raise NotImplementedError("Only component parameters are currently supported.")
        try:
            component = next(c for c in process.args.components if c.args.name == param.object_name)
        except StopIteration:
            raise ValueError(f"Component {param.object_name} not found in process.")
        if param.field_type == "arg":
            setattr(component.args, param.field_name, value)
        elif param.field_type == "initial_value":
            component.args.initial_values[param.field_name] = value

    @staticmethod
    def _get_objective(process: Process, objective: ObjectiveSpec) -> _t.Any:  # pragma: no cover
        if objective.object_type != "component":
            raise NotImplementedError("Only component objectives are currently supported.")
        component = process.components[objective.object_name]
        return getattr(component, objective.field_name)

    @staticmethod
    async def _run_process(process: Process) -> None:  # pragma: no cover
        async with process:
            await process.run()

    @property
    def is_multi_objective(self) -> bool:
        """Returns `True` if the optimisation is multi-objective."""
        return len(self._objective) > 1

    def run(self, spec: ProcessSpec) -> ray.tune.Result | list[ray.tune.Result]:
        """Run the optimisation job on Ray.

        Args:
            spec: The [`ProcessSpec`][plugboard.schemas.ProcessSpec] to optimise.

        Returns:
            Either one or a list of [`Result`][ray.tune.Result] objects containing the best trial
            result. Use the `result_grid` property to get full trial results.
        """
        self._logger.info("Running optimisation job on Ray")
        spec = spec.model_copy()
        # The Ray worker won't necessarily have the same registry as the driver, so we need to
        # re-register the classes in the worker
        required_classes = {c.type: ComponentRegistry.get(c.type) for c in spec.args.components}

        # See https://github.com/ray-project/ray/issues/24445 and
        # https://docs.ray.io/en/latest/tune/api/doc/ray.tune.execution.placement_groups.PlacementGroupFactory.html
        trainable_with_resources = ray.tune.with_resources(
            self._build_objective(required_classes, spec),
            ray.tune.PlacementGroupFactory(
                # Reserve 0.5 CPU for the tune process and 0.5 CPU for each component in the Process
                # TODO: Implement better resource allocation based on Process requirements
                [{"CPU": 0.5}] + [{"CPU": 0.5}] * len(spec.args.components),
            ),
        )

        self._logger.info("Setting Tuner with parameters", params=list(self._parameters.keys()))
        _tune = ray.tune.Tuner(
            trainable_with_resources,
            param_space=self._parameters,
            tune_config=self._config,
        )
        self._logger.info("Starting Tuner")
        self._result_grid = _tune.fit()
        self._logger.info("Tuner finished")
        if self.is_multi_objective:
            return [
                self._result_grid.get_best_result(metric=metric, mode=mode)
                for metric, mode in zip(self._metric, self._mode)
            ]
        if isinstance(self._metric, list) or isinstance(self._mode, list):  # pragma: no cover
            raise RuntimeError("Invalid configuration found for single-objective optimisation.")
        return self._result_grid.get_best_result(metric=self._metric, mode=self._mode)

    def _build_objective(
        self, component_classes: dict[str, type[Component]], spec: ProcessSpec
    ) -> _t.Callable:
        def fn(config: dict[str, _t.Any]) -> dict[str, _t.Any]:  # pragma: no cover
            # Recreate the ComponentRegistry in the Ray worker
            for key, cls in component_classes.items():
                ComponentRegistry.add(cls, key=key)

            for name, value in config.items():
                self._override_parameter(spec, self._parameters_dict[name], value)

            process = ProcessBuilder.build(spec)
            result = {}
            try:
                run_coro_sync(self._run_process(process))
                result = {
                    obj.full_name: self._get_objective(process, obj) for obj in self._objective
                }
            except* ConstraintError as e:
                modes = self._mode if isinstance(self._mode, list) else [self._mode]
                self._logger.warning(
                    "Constraint violated during optimisation, stopping early",
                    constraint_error=str(e),
                )
                result = {
                    obj.full_name: math.inf if mode == "min" else -math.inf
                    for obj, mode in zip(self._objective, modes)
                }

            return result

        return fn
