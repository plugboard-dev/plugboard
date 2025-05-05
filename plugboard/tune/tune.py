"""Provides `Tuner` class for optimising Plugboard processes."""

from pydoc import locate
import typing as _t

import ray.tune.search.optuna

from plugboard.process import Process, ProcessBuilder
from plugboard.schemas import Direction, ObjectiveSpec, OptunaSpec, ParameterSpec, ProcessSpec
from plugboard.utils.dependencies import depends_on_optional


try:
    import ray.tune
    import ray.tune.search
except ImportError:
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
            max_concurrent: The maximum number of concurrent trials. Defaults to None.
            algorithm: Configuration for the underlying Optuna algorithm used for optimisation.
        """
        self._objective = objective if isinstance(objective, list) else [objective]
        self._mode = [str(m) for m in mode] if isinstance(mode, list) else [str(mode)]
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

    def _build_algorithm(
        self, algorithm: _t.Optional[OptunaSpec] = None
    ) -> ray.tune.search.Searcher:
        if algorithm:
            _algo_kwargs = {
                **algorithm.model_dump(exclude={"type"}),
                "mode": self._mode,
                "metric": self._metric,
            }
            algo_cls: _t.Optional[_t.Any] = locate(algorithm.type)
            if not algo_cls or not issubclass(algo_cls, ray.tune.search.searcher.Searcher):
                raise ValueError(f"Could not locate `Searcher` class {algorithm.type}")
            return algo_cls(**_algo_kwargs)
        return ray.tune.search.optuna.OptunaSearch(
            metric=self._metric,
            mode=self._mode,
        )

    def _build_parameter(
        self, parameter: ParameterSpec
    ) -> tuple[str, ray.tune.search.sample.Sampler]:
        parameter_cls: _t.Optional[_t.Any] = locate(parameter.type)
        if not parameter_cls or parameter_cls not in _t.get_args(ParameterSpec):
            raise ValueError(f"Could not locate parameter class {parameter.type}")
        return parameter.full_name, parameter_cls(
            # The schema will exclude the object and field names and types
            **parameter.model_dump()
        )

    @staticmethod
    def _override_parameter(process: ProcessSpec, param: ParameterSpec, value: _t.Any) -> None:
        if param.object != "component":
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
    def _get_objective(process: Process, objective: ObjectiveSpec) -> _t.Any:
        if objective.object != "component":
            raise NotImplementedError("Only component objectives are currently supported.")
        component = process.components[objective.object_name]
        return getattr(component, objective.field_name)

    async def run(self, spec: ProcessSpec) -> None:
        """Run the optimisation job on Ray.

        Args:
            spec: The [`ProcessSpec`][plugboard.schemas.ProcessSpec] to optimise.
        """
        spec = spec.model_copy()

        async def _objective(config: dict[str, _t.Any]) -> _t.Any:
            for name, value in config.items():
                self._override_parameter(spec, self._parameters_dict[name], value)
            process = ProcessBuilder.build(spec)
            async with process:
                await process.run()
            return {obj.full_name: self._get_objective(process, obj) for obj in self._objective}

        # See https://github.com/ray-project/ray/issues/24445 and
        # https://docs.ray.io/en/latest/tune/api/doc/ray.tune.execution.placement_groups.PlacementGroupFactory.html
        trainable_with_resources = ray.tune.with_resources(
            _objective,
            ray.tune.PlacementGroupFactory(
                # Reserve 1 CPU for the tune process and 1 CPU for each component in the Process
                # TODO: Implement better resource allocation based on Process requirements
                [{"CPU": 1.0}] + [{"CPU": 1.0}] * len(spec.args.components),
            ),
        )

        self._tune = ray.tune.Tuner(
            trainable_with_resources,
            param_space=self._parameters,
            tune_config=self._config,
        )
