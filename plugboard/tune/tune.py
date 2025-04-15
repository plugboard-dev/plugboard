"""Provides `Tuner` class for optimising Plugboard processes."""

from pydoc import locate
import typing as _t

import ray.tune.search.optuna

from plugboard.schemas import Direction, OptunaSpec, ParameterSpec, ProcessSpec
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
        objective: str | list[str],
        parameters: list[ParameterSpec],
        num_samples: int,
        mode: Direction | list[list[Direction]] = "max",
        max_concurrent: _t.Optional[int] = None,
        algorithm: _t.Optional[OptunaSpec] = None,
    ) -> None:
        """Instantiates the `Tuner` class.

        Args:
            objective: The location of the objective(s) to optimise for in the `Process`.
            parameters: The parameters to optimise over.
            num_samples: The number of trial samples to use for the optimisation.
            mode: The direction of the optimisation.
            max_concurrent: The maximum number of concurrent trials. Defaults to None.
            algorithm: Configuration for the underlying Optuna algorithm used for optimisation.
        """
        self._objective = objective
        self._parameter_locations = {p.name: p.location for p in parameters}
        self._parameters = dict(self._build_parameter(p) for p in parameters)
        if algorithm:
            algo_cls: _t.Optional[_t.Any] = locate(algorithm.type)
            if not algo_cls or not issubclass(algo_cls, ray.tune.search.SearchAlgorithm):
                raise ValueError(f"Could not locate algorithm class {algorithm.type}")
            _algo = algo_cls()
        else:
            _algo = ray.tune.search.optuna.OptunaSearch()
        if max_concurrent is not None:
            _algo = ray.tune.search.ConcurrencyLimiter(_algo, max_concurrent)
        self._config = ray.tune.TuneConfig(
            mode=mode,
            num_samples=num_samples,
            search_alg=_algo,
        )

    def _build_parameter(self, parameter: ParameterSpec) -> tuple[str, ray.tune.search.Parameter]:
        parameter_cls: _t.Optional[_t.Any] = locate(parameter.type)
        if not parameter_cls or parameter_cls not in _t.get_args(ParameterSpec):
            raise ValueError(f"Could not locate parameter class {parameter.type}")
        return parameter.name, parameter_cls(
            **parameter.model_dump(exclude={"type", "name", "location"})
        )

    def run(self, spec: ProcessSpec) -> None:
        """Run the optimisation job on Ray.

        Args:
            spec: The [`ProcessSpec`][plugboard.schemas.ProcessSpec] to optimise.
        """

        def _objective(config: dict[str, _t.Any]) -> _t.Any:
            # for name, value in config.items():
            #    location = self._parameter_locations[name]
            # process = ProcessBuilder.build(spec)
            # TODO: Implement this
            return None

        self._tune = ray.tune.Tuner(
            _objective,
            param_space=[],
            tune_config=self._config,
        )
