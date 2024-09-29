"""Provides `StateBackend` base class for managing process state."""

from abc import ABC, abstractmethod
import asyncio
from datetime import datetime, timezone
import typing as _t

from plugboard.utils import AsDictMixin, EntityIdGen


if _t.TYPE_CHECKING:
    from plugboard.component import Component
    from plugboard.connector import Connector
    from plugboard.process import Process


class StateBackend(ABC, AsDictMixin):
    """`StateBackend` defines an interface for managing process state."""

    def __init__(self, job_id: _t.Optional[str] = None):
        """Instantiates `StateBackend`.

        Args:
            job_id: The unique id for the job.
        """
        loop = asyncio.get_event_loop()

        _job_id = job_id or EntityIdGen.job_id()
        if not EntityIdGen.is_job_id(_job_id):
            raise ValueError(f"Invalid job id: {_job_id}")
        loop.run_until_complete(self._set("job_id", _job_id))

        if job_id is None:
            _created_at = datetime.now(timezone.utc).isoformat()
        else:
            # TODO : Retrieve information for existing state.
            _created_at = "unset"
        loop.run_until_complete(self._set("created_at", _created_at))

    @abstractmethod
    async def _get(self, key: str | tuple[str], value: _t.Optional[_t.Any] = None) -> _t.Any:
        """Returns a value from the state."""
        pass

    @abstractmethod
    async def _set(self, key: str | tuple[str], value: _t.Any) -> None:
        """Sets a value in the state."""
        pass

    @property
    async def job_id(self) -> str:
        """Returns the job id for the state."""
        return await self._get("job_id")

    @property
    async def created_at(self) -> str:
        """Returns date and time of job creation."""
        return await self._get("created_at")

    async def upsert_process(self, process: Process) -> None:
        """Upserts a process into the state."""
        pass

    async def get_process(self, process_id: str) -> dict:
        """Returns a process from the state."""
        return {}

    async def upsert_component(
        self, component: Component, process_id: _t.Optional[str] = None
    ) -> None:
        """Upserts a component into the state."""
        pass

    async def get_component(self, component_id: str) -> dict:
        """Returns a component from the state."""
        return {}

    async def upsert_connector(
        self, connector: Connector, process_id: _t.Optional[str] = None
    ) -> None:
        """Upserts a connector into the state."""
        pass

    async def get_connector(self, connector_id: str) -> dict:
        """Returns a connector from the state."""
        return {}
