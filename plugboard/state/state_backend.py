"""Provides `StateBackend` base class for managing process state."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import typing as _t

from plugboard.utils import AsDictMixin, EntityIdGen


if _t.TYPE_CHECKING:
    from plugboard.component import Component
    from plugboard.connector import Connector
    from plugboard.process import Process


class StateBackend(ABC, AsDictMixin):
    """`StateBackend` defines an interface for managing process state."""

    def __init__(
        self, job_id: _t.Optional[str] = None, metadata: _t.Optional[dict] = None, **kwargs: _t.Any
    ) -> None:
        """Instantiates `StateBackend`.

        Args:
            job_id: The unique id for the job.
            metadata: Metadata key value pairs.
            kwargs: Additional keyword arguments.
        """
        self._local_state = {"job_id": job_id, "metadata": metadata, **kwargs}

    async def init(self) -> None:
        """Initialises the `StateBackend`."""
        await self._initialise_data(**self._local_state)

    async def destroy(self) -> None:
        """Destroys the `StateBackend`."""
        pass

    async def _initialise_data(
        self, job_id: _t.Optional[str] = None, metadata: _t.Optional[dict] = None, **kwargs: _t.Any
    ) -> None:
        """Initialises the state data."""
        _job_id = job_id or EntityIdGen.job_id()
        if not EntityIdGen.is_job_id(_job_id):
            raise ValueError(f"Invalid job id: {_job_id}")
        await self._set("job_id", _job_id)

        if job_id is None:
            _created_at = datetime.now(timezone.utc).isoformat()
        else:
            # TODO : Retrieve information for existing state.
            _created_at = "unset"
        await self._set("created_at", _created_at)

        _metadata = metadata or dict()
        await self._set("metadata", _metadata)

        comp_proc_map: dict = dict()
        await self._set("_comp_proc_map", comp_proc_map)

        conn_proc_map: dict = dict()
        await self._set("_conn_proc_map", conn_proc_map)

    @abstractmethod
    async def _get(self, key: str | tuple[str, ...], value: _t.Optional[_t.Any] = None) -> _t.Any:
        """Returns a value from the state."""
        pass

    @abstractmethod
    async def _set(self, key: str | tuple[str, ...], value: _t.Any) -> None:
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

    @property
    async def metadata(self) -> dict:
        """Returns metadata attached to the job."""
        return await self._get("metadata")

    async def upsert_process(self, process: Process) -> None:
        """Upserts a process into the state."""
        await self._set(("process", process.id), process.dict())
        # TODO : Need to make this transactional.
        comp_proc_map = await self._get("_comp_proc_map")
        comp_proc_map.update({c.id: process.id for c in process.components.values()})
        await self._set("_comp_proc_map", comp_proc_map)
        # TODO : Need to make this transactional.
        conn_proc_map = await self._get("_conn_proc_map")
        conn_proc_map.update({c.id: process.id for c in process.connectors.values()})
        await self._set("_conn_proc_map", conn_proc_map)

    async def get_process(self, process_id: str) -> dict:
        """Returns a process from the state."""
        return await self._get(("process", process_id))

    async def upsert_component(self, component: Component) -> None:
        """Upserts a component into the state."""
        process_id = await self._get(("_comp_proc_map", component.id))
        key = ("process", process_id, "component", component.id)
        await self._set(key, component.dict())

    async def get_component(self, component_id: str) -> dict:
        """Returns a component from the state."""
        return await self._get(("component", component_id))

    async def upsert_connector(self, connector: Connector) -> None:
        """Upserts a connector into the state."""
        process_id = await self._get(("_conn_proc_map", connector.id))
        key = ("process", process_id, "connector", connector.id)
        await self._set(key, connector.dict())

    async def get_connector(self, connector_id: str) -> dict:
        """Returns a connector from the state."""
        return await self._get(("connector", connector_id))
