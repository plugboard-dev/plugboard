"""Provides the `TuneSpec` class for configuring optimisation jobs."""

from abc import ABC
import typing as _t

from pydantic import Field, PositiveInt, model_validator

from plugboard.schemas._common import PlugboardBaseModel


class OptunaSpec(PlugboardBaseModel):
    """Specification for the Optuna configuration.

    See: https://docs.ray.io/en/latest/tune/api/doc/ray.tune.search.optuna.OptunaSearch.html
    and https://optuna.readthedocs.io/en/stable/reference/index.html for more information on the
    Optuna configuration.

    Attributes:
        type: The algorithm type to load.
        space: Optional; A function defining the search space. Use this to define more complex
            search spaces that cannot be represented using the built-in parameter types.
        study_name: Optional; The name of the study.
        storage: Optional; The storage URI to save the optimisation results to.
    """

    type: _t.Literal["ray.tune.search.optuna.OptunaSearch"] = "ray.tune.search.optuna.OptunaSearch"
    space: str | None = None
    study_name: str | None = None
    storage: str | None = None


class BaseFieldSpec(PlugboardBaseModel, ABC):
    """Base class for specifying fields within a Plugboard [`Process`][plugboard.process.Process].

    These fields may be used as adjustable parameter inputs or as an optimisation objective.

    Attributes:
        object_type: The type of object on which the field is defined. Defaults to "component".
        object_name: The name of the object on which the field is defined.
        field_type: The type of field. This can be "arg", "initial_value", or "field".
        field_name: The name of the field.
    """

    object_type: _t.Literal["component"] = Field("component", exclude=True)
    object_name: str = Field(..., exclude=True)
    field_type: _t.Literal["arg", "initial_value", "field"] = Field(..., exclude=True)
    field_name: str = Field(..., exclude=True)

    @property
    def full_name(self) -> str:
        """Returns the full name of the field, including the object name and field name."""
        return f"{self.object_name}.{self.field_name}"


class ObjectiveSpec(BaseFieldSpec):
    """Specification for an objective field."""

    @model_validator(mode="before")
    @classmethod
    def _fill_defaults(
        cls, data: dict[str, _t.Any] | list[dict[str, _t.Any]]
    ) -> dict[str, _t.Any] | list[dict[str, _t.Any]]:
        if isinstance(data, list):
            # If the data is a list, skip because it is already a list of objectives
            return data
        if "field_type" not in data:
            data["field_type"] = "field"
        if data["field_type"] != "field":  # pragma: no cover
            raise ValueError("The field type must be 'field' for an objective specification.")
        return data


class FloatParameterSpec(BaseFieldSpec):
    """Specification for a uniform float parameter.

    See: https://docs.ray.io/en/latest/tune/api/search_space.html.

    Attributes:
        type: The type of the parameter.
        lower: The lower bound of the parameter.
        upper: The upper bound of the parameter.
    """

    type: _t.Literal["ray.tune.uniform"] = "ray.tune.uniform"
    lower: float
    upper: float


class IntParameterSpec(BaseFieldSpec):
    """Specification for a uniform integer parameter.

    See: https://docs.ray.io/en/latest/tune/api/search_space.html.

    Attributes:
        type: The type of the parameter.
        lower: The lower bound of the parameter.
        upper: The upper bound of the parameter.
    """

    type: _t.Literal["ray.tune.randint"] = "ray.tune.randint"
    lower: int
    upper: int


class CategoricalParameterSpec(BaseFieldSpec):
    """Specification for a categorical parameter.

    See: https://docs.ray.io/en/latest/tune/api/search_space.html.

    Attributes:
        type: The type of the parameter.
        categories: The categories of the parameter.
    """

    type: _t.Literal["ray.tune.choice"] = "ray.tune.choice"
    categories: list[_t.Any]


ParameterSpec = _t.Union[
    FloatParameterSpec,
    IntParameterSpec,
    CategoricalParameterSpec,
]
"""A union type for all parameter specifications."""

Direction = _t.Literal["min", "max"]
"""A type for the direction of optimisation."""


class TuneArgsDict(_t.TypedDict):
    """`TypedDict` of the [`Tuner`][plugboard.tune.Tuner] constructor arguments."""

    objective: str | list[str]
    parameters: list[ParameterSpec]
    num_samples: int
    mode: _t.NotRequired[Direction | list[Direction]]
    max_concurrent: _t.NotRequired[int | None]
    algorithm: OptunaSpec


class TuneArgsSpec(PlugboardBaseModel):
    """Specification of the arguments for the `Tune` class.

    Attributes:
        objective: The location of the objective(s) to optimise for in the `Process`.
        parameters: The parameters to optimise over.
        num_samples: The number of samples to draw during the optimisation.
        mode: The mode of optimisation. For multi-objective optimisation, this should be a list
            containing a direction for each objective.
        max_concurrent: The maximum number of concurrent trials.
        algorithm: The algorithm to use for the optimisation.
    """

    objective: ObjectiveSpec | list[ObjectiveSpec]
    parameters: list[ParameterSpec] = Field(min_length=1)
    num_samples: PositiveInt
    mode: Direction | list[Direction] = "max"
    max_concurrent: PositiveInt | None = None
    algorithm: _t.Union[OptunaSpec] = Field(OptunaSpec(), discriminator="type")

    @model_validator(mode="after")
    def _validate_model(self: _t.Self) -> _t.Self:
        if isinstance(self.mode, list):
            if not isinstance(self.objective, list):
                raise ValueError(
                    "In multi-objective optimisation, both `mode` and `objective` must be lists."
                )
            if len(self.mode) != len(self.objective):
                raise ValueError("The length of `mode` must match the length of `objective`.")
        return self


class TuneSpec(PlugboardBaseModel):
    """Configuration for an optimisation job.

    Attributes:
        args: The arguments for the `Tune` job.
    """

    args: TuneArgsSpec
