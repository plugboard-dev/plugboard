"""Provides `StateBackend` base class for managing process state."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import ExitStack
from datetime import datetime, timezone
from functools import cache
from types import TracebackType
import typing as _t

from that_depends import ContextScopes, Provide, container_context, inject

from plugboard.exceptions import NotFoundError
from plugboard.schemas.state import Status
from plugboard.utils import DI, ExportMixin


if _t.TYPE_CHECKING:  # pragma: no cover
    from plugboard.component import Component
    from plugboard.connector import Connector
    from plugboard.process import Process


class StateBackend(ABC, ExportMixin):
    """`StateBackend` defines an interface for managing process state."""

    _id_separator: str = ":"

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
        self._initialised_with_job_id = False
        self._logger = DI.logger.resolve_sync().bind(cls=self.__class__.__name__, job_id=job_id)
        self._logger.info("StateBackend created")
        self._ctx = ExitStack()

    def __getstate__(self) -> dict:
        state = self.__dict__.copy()
        state.pop("_ctx", None)
        return state

    def __setstate__(self, state: dict) -> None:
        self.__dict__.update(state)
        self._ctx = ExitStack()
        job_id = self._local_state.get("job_id")
        self._enter_container_context(job_id)

    async def init(self) -> None:
        """Initialises the `StateBackend`."""
        job_id = self._local_state.pop("job_id", None)
        self._initialised_with_job_id = job_id is not None
        self._enter_container_context(job_id)
        await self._initialise_data(**self._local_state)
        self._logger = self._logger.bind(job_id=self.job_id)

    async def destroy(self) -> None:
        """Destroys the `StateBackend`."""
        self._ctx.close()
        if not self._initialised_with_job_id:
            self._local_state["job_id"] = None
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

    @cache
    def _get_db_id(self, entity_id: str) -> str:
        """Returns the database id for a given entity id.

        The database id for an entity is the entity id prefixed with the job id.
        If the provided entity id includes the job id, it is returned as is;
        otherwise, the job id is prefixed to the entity id.
        """
        id_parts = entity_id.split(self._id_separator)
        if len(id_parts) == 1:
            return f"{self.job_id}{self._id_separator}{entity_id}"
        if len(id_parts) != 2:
            raise ValueError(f"Invalid entity id: {entity_id}")
        if id_parts[0] != self.job_id:
            raise ValueError(f"Entity id {entity_id} does not belong to job {self.job_id}")
        return entity_id

    def _strip_job_id(self, db_id: str) -> str:
        """Strips the job id from a database id to return the entity id."""
        id_parts = db_id.split(self._id_separator)
        if len(id_parts) != 2:
            raise ValueError(f"Invalid database id: {db_id}")
        if id_parts[0] != self.job_id:
            raise ValueError(f"Database id {db_id} does not belong to job {self.job_id}")
        return id_parts[1]

    def _enter_container_context(self, job_id: _t.Optional[str] = None) -> None:
        """Enters the container context with the job_id."""
        # Enter the container context with the job_id (same for both fresh init and reinit)
        container_cm = container_context(
            DI, global_context={"job_id": job_id}, scope=ContextScopes.APP
        )
        self._ctx.enter_context(container_cm)

    @inject
    async def _initialise_data(
        self, job_id: str = Provide[DI.job_id], metadata: _t.Optional[dict] = None, **kwargs: _t.Any
    ) -> None:
        """Initialises the state data."""
        try:
            # TODO : Requires indication of new or existing job to conditionally raise exception?
            job_data = await self._get_job(job_id)
            if metadata:
                job_data.setdefault("metadata", {}).update(metadata)
                await self._upsert_job(job_data)
        except NotFoundError:
            job_data = {
                "job_id": job_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "metadata": metadata or {},
            }
            await self._upsert_job(job_data)
        self._local_state.update(job_data)

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
            process_data["components"] = {k: {} for k in process_data["components"].keys()}
            process_data["connectors"] = {k: {} for k in process_data["connectors"].keys()}
        await self._set(self._process_key(process.id), process_data)
        await self.update_process_status(process.id, process.status)
        # TODO : Need to make this transactional.
        comp_proc_map = await self._get("_comp_proc_map", {})
        comp_proc_map.update({c.id: process.id for c in process.components.values()})
        await self._set("_comp_proc_map", comp_proc_map)
        # TODO : Need to make this transactional.
        conn_proc_map = await self._get("_conn_proc_map", {})
        conn_proc_map.update({c.id: process.id for c in process.connectors.values()})
        await self._set("_conn_proc_map", conn_proc_map)

    async def get_process(self, process_id: str) -> dict:
        """Returns a process from the state."""
        return await self._get(self._process_key(process_id))

    async def _get_process_id_for_component(self, component_id: str) -> str:
        process_id: str | None = await self._get(("_comp_proc_map", component_id))
        if process_id is None:
            raise NotFoundError(f"No process found for component with ID {component_id}")
        return process_id

    async def get_process_for_component(self, component_id: str) -> dict:
        """Gets the process that a component belongs to."""
        process_id = await self._get_process_id_for_component(component_id)
        return await self.get_process(process_id)

    async def upsert_component(self, component: Component) -> None:
        """Upserts a component into the state."""
        process_id = await self._get_process_id_for_component(component.id)
        key = self._component_key(process_id, component.id)
        await self._set(key, component.dict())
        if component.status in {Status.FAILED}:
            # If the component is terminal, update the process status
            await self.update_process_status(process_id, component.status)

    async def get_component(self, component_id: str) -> dict:
        """Returns a component from the state."""
        process_id = await self._get_process_id_for_component(component_id)
        key = self._component_key(process_id, component_id)
        return await self._get(key)

    async def _get_process_id_for_connector(self, connector_id: str) -> str:
        process_id: str | None = await self._get(("_conn_proc_map", connector_id))
        if process_id is None:
            raise NotFoundError(f"No process found for connector with ID {connector_id}")
        return process_id

    async def upsert_connector(self, connector: Connector) -> None:
        """Upserts a connector into the state."""
        process_id = await self._get_process_id_for_connector(connector.id)
        key = self._connector_key(process_id, connector.id)
        await self._set(key, connector.dict())

    async def get_connector(self, connector_id: str) -> dict:
        """Returns a connector from the state."""
        process_id = await self._get_process_id_for_connector(connector_id)
        key = self._connector_key(process_id, connector_id)
        return await self._get(key)

    async def update_process_status(self, process_id: str, status: Status) -> None:
        """Updates the status of a process in the state."""
        process_status_key = self._process_key(process_id) + ("status",)
        await self._set(process_status_key, str(status))

    async def get_process_status(self, process_id: str) -> Status:
        """Gets the status of a process from the state."""
        process_status_key = self._process_key(process_id) + ("status",)
        status_str: str | None = await self._get(process_status_key)
        if status_str is None:
            raise NotFoundError(f"Process with id {process_id} not found.")
        return Status(status_str)

    async def get_process_status_for_component(self, component_id: str) -> Status:
        """Gets the status of the process that a component belongs to."""
        process_id = await self._get_process_id_for_component(component_id)
        return await self.get_process_status(process_id)
