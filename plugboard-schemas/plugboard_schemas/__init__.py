"""Provides schemas used in Plugboard.

This includes:

* Pydantic models for specifying Plugboard objects;
* `TypeDict` definitions for constructor `**kwargs`.
"""

from importlib.metadata import version

from ._common import PlugboardBaseModel
from ._graph import simple_cycles
from ._validation import (
    ValidationError,
    validate_all_inputs_connected,
    validate_input_events,
    validate_no_unresolved_cycles,
)
from .component import ComponentArgsDict, ComponentArgsSpec, ComponentSpec, Resource
from .config import ConfigSpec, ProcessConfigSpec
from .connector import (
    DEFAULT_CONNECTOR_CLS_PATH,
    ConnectorBuilderArgsDict,
    ConnectorBuilderArgsSpec,
    ConnectorBuilderSpec,
    ConnectorMode,
    ConnectorSocket,
    ConnectorSpec,
)
from .entities import ENTITY_ID_REGEX, Entity
from .io import IODirection
from .process import ProcessArgsDict, ProcessArgsSpec, ProcessSpec
from .state import (
    DEFAULT_STATE_BACKEND_CLS_PATH,
    RAY_STATE_BACKEND_CLS_PATH,
    StateBackendArgsDict,
    StateBackendArgsSpec,
    StateBackendSpec,
    Status,
)
from .tune import (
    CategoricalParameterSpec,
    Direction,
    FloatParameterSpec,
    IntParameterSpec,
    ObjectiveSpec,
    OptunaSpec,
    ParameterSpec,
    TuneArgsDict,
    TuneArgsSpec,
    TuneSpec,
)


__version__ = version(__package__)


__all__ = [
    "CategoricalParameterSpec",
    "ComponentSpec",
    "ComponentArgsDict",
    "ComponentArgsSpec",
    "ConfigSpec",
    "ConnectorBuilderArgsDict",
    "ConnectorBuilderArgsSpec",
    "ConnectorBuilderSpec",
    "ConnectorMode",
    "ConnectorSocket",
    "ConnectorSpec",
    "DEFAULT_CONNECTOR_CLS_PATH",
    "DEFAULT_STATE_BACKEND_CLS_PATH",
    "Direction",
    "ENTITY_ID_REGEX",
    "Entity",
    "FloatParameterSpec",
    "IntParameterSpec",
    "IODirection",
    "ObjectiveSpec",
    "OptunaSpec",
    "ParameterSpec",
    "PlugboardBaseModel",
    "ProcessConfigSpec",
    "ProcessSpec",
    "ProcessArgsDict",
    "ProcessArgsSpec",
    "RAY_STATE_BACKEND_CLS_PATH",
    "Resource",
    "StateBackendSpec",
    "StateBackendArgsDict",
    "StateBackendArgsSpec",
    "Status",
    "TuneArgsDict",
    "TuneArgsSpec",
    "TuneSpec",
    "ValidationError",
    "simple_cycles",
    "validate_all_inputs_connected",
    "validate_input_events",
    "validate_no_unresolved_cycles",
]
