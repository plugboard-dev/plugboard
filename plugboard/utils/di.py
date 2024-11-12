"""Provides dependency injection utilities."""

import inject
from multiprocess import Manager
from multiprocess.managers import SyncManager


def _configure(binder: inject.Binder) -> None:
    """Configures the DI container.

    Provides:
    * A shared multiprocessing Manager object.
    """
    binder.bind_to_constructor(SyncManager, Manager)


inject.configure(_configure)
