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
        # Validate and normalize objective/mode
        self._check_objective(objective, mode)
        self._objective, self._mode, self._metric = self._normalize_objective_and_mode(
            objective, mode
        )
        self._custom_space = bool(algorithm and algorithm.space)

        # Prepare parameters and search algorithm
        self._parameters_dict, self._parameters = self._prepare_parameters(parameters)
        searcher = self._init_search_algorithm(algorithm, max_concurrent)

        # Configure Ray Tune
        self._config = ray.tune.TuneConfig(num_samples=num_samples, search_alg=searcher)
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
            return self._default_searcher()

        algo_kwargs = self._build_algo_kwargs(algorithm)
        algo_cls = self._get_algo_class(algorithm.type)
        self._logger.info(
            "Using custom search algorithm",
            algorithm=algorithm.type,
            params={k: self._mask_param_value(k, v) for k, v in algo_kwargs.items()},
        )
        return algo_cls(**algo_kwargs)

    def _default_searcher(self) -> "ray.tune.search.Searcher":
        return ray.tune.search.optuna.OptunaSearch(metric=self._metric, mode=self._mode)

    def _build_algo_kwargs(self, algorithm: OptunaSpec) -> dict[str, _t.Any]:
        """Prepare keyword args for the searcher, normalising storage/space."""
        kwargs = algorithm.model_dump(exclude={"type"})
        kwargs["mode"] = self._mode
        kwargs["metric"] = self._metric

        storage = kwargs.get("storage")
        if isinstance(storage, str):
            kwargs["storage"] = optuna.storages.RDBStorage(url=storage)
            self._logger.info(
                "Converted storage URI to Optuna RDBStorage object",
                storage_uri=storage,
            )

        space = kwargs.get("space")
        if space is not None:
            kwargs["space"] = self._resolve_space_fn(space)

        return kwargs

    def _resolve_space_fn(self, space: str) -> _t.Callable:
        space_fn = locate(space)
        if not space_fn or not isfunction(space_fn):  # pragma: no cover
            raise ValueError(f"Could not locate search space function {space}")
        return space_fn

    def _get_algo_class(self, type_path: str) -> _t.Type[ray.tune.search.searcher.Searcher]:
        algo_cls: _t.Optional[_t.Any] = locate(type_path)
        if not algo_cls or not issubclass(
            algo_cls, ray.tune.search.searcher.Searcher
        ):  # pragma: no cover
            raise ValueError(f"Could not locate `Searcher` class {type_path}")
        return algo_cls

    def _mask_param_value(self, k: str, v: _t.Any) -> _t.Any:
        if k == "storage" or (k == "space" and isfunction(v)):
            return f"<{type(v).__name__}>"
        return v

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

        tuner_kwargs: dict[str, _t.Any] = {
            "tune_config": self._config,
        }
        if not self._custom_space:
            self._logger.info("Setting Tuner with parameters", params=list(self._parameters.keys()))
            tuner_kwargs["param_space"] = self._parameters
        else:
            self._logger.info("Setting Tuner with custom search space")

        _tune = ray.tune.Tuner(trainable_with_resources, **tuner_kwargs)
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
                if name not in self._parameters_dict:
                    # Custom search spaces may include intermediate parameters not in the Tuner
                    self._logger.warning("Parameter from config not found in Tuner", param=name)
                    continue
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

    def _normalize_objective_and_mode(
        self,
        objective: ObjectiveSpec | list[ObjectiveSpec],
        mode: Direction | list[Direction],
    ) -> tuple[list[ObjectiveSpec], str | list[str], str | list[str]]:
        """Return normalized objectives, modes and metric name(s)."""
        objectives = objective if isinstance(objective, list) else [objective]
        modes = [str(m) for m in mode] if isinstance(mode, list) else str(mode)
        metric = (
            [obj.full_name for obj in objectives]
            if len(objectives) > 1
            else objectives[0].full_name
        )
        return objectives, modes, metric

    def _prepare_parameters(
        self, parameters: list[ParameterSpec]
    ) -> tuple[dict[str, ParameterSpec], dict[str, "ray.tune.search.sample.Sampler"]]:
        """Build parameter lookup dict and Ray Tune parameter space."""
        params_dict = {p.full_name: p for p in parameters}
        params_space = dict(self._build_parameter(p) for p in parameters)
        return params_dict, params_space

    def _init_search_algorithm(
        self, algorithm: _t.Optional[OptunaSpec], max_concurrent: _t.Optional[int]
    ) -> "ray.tune.search.Searcher":
        """Create the search algorithm and apply concurrency limits if requested."""
        algo = self._build_algorithm(algorithm)
        if max_concurrent is not None:
            algo = ray.tune.search.ConcurrencyLimiter(algo, max_concurrent)
        return algo
