"""Provides `StateBackend` base class for managing process state."""

from abc import ABC
from datetime import datetime, timezone
import typing as _t

from plugboard.utils import AsDictMixin, EntityIdGen


class StateBackend(ABC, AsDictMixin):
    """`StateBackend` defines an interface for managing process state."""

    def __init__(self, job_id: _t.Optional[str] = None):
        """Instantiates `StateBackend`.

        Args:
            job_id: The unique id for the job.
        """
        self._job_id = job_id or EntityIdGen.job_id()
        if not EntityIdGen.is_job_id(self._job_id):
            raise ValueError(f"Invalid job id: {self._job_id}")
        if job_id is None:
            self._created_at = datetime.now(timezone.utc).isoformat()
        else:
            # TODO : Retrieve information for existing state.
            self._created_at = "unset"
            pass

    @property
    def job_id(self) -> str:
        """Returns the job id for the state."""
        return self._job_id

    @property
    def created_at(self) -> str:
        """Returns date and time of job creation."""
        return self._created_at
