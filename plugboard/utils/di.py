"""Provides dependency injection utilities."""

import inject
import multiprocess as mp
from multiprocess.context import BaseContext
from multiprocess.managers import SyncManager


def _configure(binder: inject.Binder) -> None:
    """Configures the DI container.

    Provides:
    * A multiprocess spawn context.
    * A shared multiprocess Manager object.
    """
    ctx = mp.get_context("spawn")
    binder.bind(BaseContext, ctx)
    binder.bind_to_constructor(SyncManager, ctx.Manager)


inject.configure(_configure)
