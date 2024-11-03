"""Provides dependency injection utilities."""

from multiprocessing import Manager
from multiprocessing.managers import SyncManager

import inject


def _configure(binder: inject.Binder) -> None:
    """Configures the DI container.

    Provides:
    * A shared multiprocessing Manager object.
    """
    binder.bind(SyncManager, Manager())


inject.configure(_configure)
