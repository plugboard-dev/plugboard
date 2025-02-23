"""Provides `StateBackend` base class for managing process state."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from types import TracebackType
import typing as _t

from plugboard.utils import DI, EntityIdGen, ExportMixin


if _t.TYPE_CHECKING:
    from plugboard.component import Component
    from plugboard.connector import Connector
    from plugboard.process import Process


class StateBackend(ABC, ExportMixin):
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
        self._logger = DI.logger.sync_resolve().bind(cls=self.__class__.__name__, job_id=job_id)
        self._logger.info("StateBackend created")

    async def init(self) -> None:
        """Initialises the `StateBackend`."""
        await self._initialise_data(**self._local_state)

    async def destroy(self) -> None:
        """Destroys the `StateBackend`."""
        pass

    async def __aenter__(self) -> StateBackend:
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

    async def _initialise_data(
        self, job_id: _t.Optional[str] = None, metadata: _t.Optional[dict] = None, **kwargs: _t.Any
    ) -> None:
        """Initialises the state data."""
        if job_id is not None:
            _job_data = await self._get_job(job_id)
        else:
            _job_data = {
                "job_id": EntityIdGen.job_id(),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "metadata": metadata or dict(),
            }
            await self._upsert_job(_job_data)
        self._local_state.update(_job_data)

    @abstractmethod
    async def _get(self, key: str | tuple[str, ...], value: _t.Optional[_t.Any] = None) -> _t.Any:
        """Returns a value from the state."""
        pass

    @abstractmethod
    async def _set(self, key: str | tuple[str, ...], value: _t.Any) -> None:
        """Sets a value in the state."""
        pass

    @property
    def job_id(self) -> str:
        """Returns the job id for the state."""
        return self._local_state["job_id"]

    @property
    def created_at(self) -> str:
        """Returns date and time of job creation."""
        return self._local_state["created_at"]

    @property
    def metadata(self) -> dict:
        """Returns metadata attached to the job."""
        return self._local_state["metadata"]

    @classmethod
    def _process_key(cls, process_id: str) -> tuple[str, ...]:
        return ("processes", process_id)

    @classmethod
    def _component_key(cls, process_id: str, component_id: str) -> tuple[str, ...]:
        return cls._process_key(process_id) + ("components", component_id)

    @classmethod
    def _connector_key(cls, process_id: str, component_id: str) -> tuple[str, ...]:
        return cls._process_key(process_id) + ("connectors", component_id)

    async def _upsert_job(self, job_data: dict) -> None:
        """Upserts a job into the state."""
        pass

    async def _get_job(self, job_id: str) -> dict:
        """Returns a job from the state."""
        raise NotImplementedError()

    async def upsert_process(self, process: Process, with_components: bool = False) -> None:
        """Upserts a process into the state."""
        # TODO : Book keeping for dynamic process components and connectors.
        process_data = process.dict()
        if with_components is False:
            process_data["components"] = {}
            process_data["connectors"] = {}
        await self._set(self._process_key(process.id), process_data)
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
        return await self._get(self._process_key(process_id))

    async def upsert_component(self, component: Component) -> None:
        """Upserts a component into the state."""
        process_id = await self._get(("_comp_proc_map", component.id))
        key = self._component_key(process_id, component.id)
        await self._set(key, component.dict())

    async def get_component(self, component_id: str) -> dict:
        """Returns a component from the state."""
        process_id = await self._get(("_comp_proc_map", component_id))
        key = self._component_key(process_id, component_id)
        return await self._get(key)

    async def upsert_connector(self, connector: Connector) -> None:
        """Upserts a connector into the state."""
        process_id = await self._get(("_conn_proc_map", connector.id))
        key = self._connector_key(process_id, connector.id)
        await self._set(key, connector.dict())

    async def get_connector(self, connector_id: str) -> dict:
        """Returns a connector from the state."""
        process_id = await self._get(("_conn_proc_map", connector_id))
        key = self._connector_key(process_id, connector_id)
        return await self._get(key)
