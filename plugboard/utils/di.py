"""Provides a dependency injection container and utils."""

import multiprocessing

from that_depends import BaseContainer
from that_depends.providers import Singleton

from plugboard.utils.settings import Settings


def _mp_set_start_method(use_fork: bool = False) -> None:
    multiprocessing.set_start_method("fork" if use_fork else "spawn")


class DI(BaseContainer):
    """`DI` is a dependency injection container for plugboard."""

    settings: Singleton[Settings] = Singleton(Settings)
    mp_ctx: Singleton[None] = Singleton(_mp_set_start_method, settings.flags.multiprocessing_fork)
