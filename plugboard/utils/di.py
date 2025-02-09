"""Provides a dependency injection container and utils."""

from that_depends import BaseContainer
from that_depends.providers import Singleton

from plugboard.utils.settings import Settings


class DI(BaseContainer):
    """`DI` is a dependency injection container for plugboard."""

    settings: Singleton[Settings] = Singleton(Settings)
