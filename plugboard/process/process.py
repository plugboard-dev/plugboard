"""Provides `Process` base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType
import typing as _t

from plugboard.component import Component
from plugboard.connector import Connector
from plugboard.exceptions import NotInitialisedError
from plugboard.state import DictStateBackend, StateBackend
from plugboard.utils import DI, ExportMixin, gen_rand_str


class Process(ExportMixin, ABC):
    """`Process` is a base class for managing components in a model."""

    _default_state_cls: _t.Type[StateBackend] = DictStateBackend

    def __init__(
        self,
        components: _t.Iterable[Component],
        connectors: _t.Iterable[Connector],
        name: _t.Optional[str] = None,
        parameters: _t.Optional[dict] = None,
        state: _t.Optional[StateBackend] = None,
    ) -> None:
        """Instantiates a `Process`.

        Args:
            components: The components in the `Process`.
            connectors: The connectors between the components.
            name: Optional; Name for this `Process`.
            parameters: Optional; Parameters for the `Process`.
            state: Optional; `StateBackend` for the `Process`.
        """
        self.name = name or f"{self.__class__.__name__}_{gen_rand_str(8)}"
        self.components: dict[str, Component] = {c.id: c for c in components}
        self.connectors: dict[str, Connector] = {c.id: c for c in connectors}
        self.parameters: dict = parameters or {}
        self._state: StateBackend = state or self._default_state_cls()
        self._state_is_connected: bool = False
        # TODO: Replace when we have state tracking in StateBackend
        self._is_initialised: bool = False
        # FIXME : Job ID unavailable for logger until state.init() is called.
        self._logger = DI.logger.resolve_sync().bind(
            cls=self.__class__.__name__, name=self.name, job_id=self.state.job_id
        )
        self._logger.info("Process created")

    @property
    def id(self) -> str:
        """Unique ID for `Process`."""
        return self.name

    @property
    def state(self) -> StateBackend:
        """State backend for the process."""
        return self._state

    @property
    def is_initialised(self) -> bool:
        """Returns whether the `Process` is initialised."""
        return self._is_initialised

    async def connect_state(self, state: _t.Optional[StateBackend] = None) -> None:
        """Connects the `Process` to the `StateBackend`."""
        if self._state_is_connected:
            return
        self._state = state or self._state
        if self._state is None:
            return
        await self._state.init()
        await self._state.upsert_process(self)
        await self._connect_state()
        self._state_is_connected = True

    @abstractmethod
    async def _connect_components(self) -> None:
        """Connect components."""
        pass

    @abstractmethod
    async def _connect_state(self) -> None:
        """Connects the `Components` and `Connectors` to the `StateBackend`."""
        pass

    @abstractmethod
    async def init(self) -> None:
        """Performs component initialisation actions."""
        self._is_initialised = True

    @abstractmethod
    async def step(self) -> None:
        """Executes a single step for the process."""
        pass

    @abstractmethod
    async def run(self) -> None:
        """Runs the process to completion."""
        if not self._is_initialised:
            raise NotInitialisedError("Process must be initialised before running")

    async def destroy(self) -> None:
        """Performs tear-down actions for the `Process` and its `Component`s."""
        try:
            await self._state.destroy()
            await DI.tear_down()
            self._logger.info("Process destroyed")
        except Exception as e:  # pragma: no cover
            self._logger.error(f"Error destroying process: {e}")
            raise
        finally:
            self._is_initialised = False
            self._state_is_connected = False

    async def __aenter__(self) -> Process:
        """Enters the context manager."""
        await self.init()
        return self

    async def __aexit__(
        self,
        exc_type: _t.Optional[_t.Type[BaseException]],
        exc_value: _t.Optional[BaseException],
        traceback: _t.Optional[TracebackType],
    ) -> None:
        """Exits the context manager."""
        await self.destroy()

    def dict(self) -> dict[str, _t.Any]:  # noqa: D102
        return {
            "id": self.id,
            "name": self.name,
            "components": {k: v.dict() for k, v in self.components.items()},
            "connectors": {k: v.dict() for k, v in self.connectors.items()},
            "parameters": self.parameters,
        }
