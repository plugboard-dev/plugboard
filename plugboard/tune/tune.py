"""Provides `Tuner` class for optimising Plugboard processes."""

from pydoc import locate
import typing as _t

import ray.tune.search.optuna

from plugboard.process import Process
from plugboard.schemas.tune import Direction, OptunaSpec, ParameterSpec
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
        parameters: _t.Optional[list[ParameterSpec]],
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
        self._parameters = parameters
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

    def _objective_function(self) -> _t.Any:
        pass

    def run(self, process: Process) -> None:
        """Run the optimisation job on Ray.

        Args:
            process: The [`Process`][plugboard.process.Process] to optimise.
        """
        # TODO: Implement the tuning logic here
        self._tune = ray.tune.Tuner()
