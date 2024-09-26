"""Provides `StateBackend` base class for managing process state."""

from abc import ABC
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

    @property
    def job_id(self) -> str:
        """Returns the job id for the state."""
        return self._job_id
