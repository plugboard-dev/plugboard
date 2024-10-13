"""Provides exceptions for Plugboard."""


class ChannelClosedError(Exception):
    """Raised when a closed channel is accessed."""

    pass


class IOStreamClosedError(Exception):
    """`IOStreamClosedError` is raised when an IO stream is closed."""

    pass


class NoMoreDataException(Exception):
    """Raised when there is no more data to fetch."""

    pass


class RegistryError(Exception):
    """Raised when an unknown class is requested from the ClassRegistry."""

    pass
