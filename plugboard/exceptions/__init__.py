"""Provides exceptions for Plugboard."""


class ChannelError(Exception):
    """Raised for channel related errors."""

    pass


class ChannelClosedError(ChannelError):
    """Raised when a closed channel is accessed."""

    pass


class ChannelNotConnectedError(ChannelError):
    """Raised when using a channel that is not connected."""

    pass


class ChannelSetupError(ChannelError):
    """Raised when a channel is setup incorrectly."""

    pass


class IOControllerError(Exception):
    """Raised for IO controller related errors."""

    pass


class IOStreamClosedError(IOControllerError):
    """`IOStreamClosedError` is raised when an IO stream is closed."""

    pass


class IOSetupError(IOControllerError):
    """Raised when an IO controller is setup incorrectly."""

    pass


class EventStreamClosedError(Exception):
    """Raised when there are no more event producers running."""

    pass


class NoMoreDataException(Exception):
    """Raised when there is no more data to fetch."""

    pass


class RegistryError(Exception):
    """Raised when an unknown class is requested from the ClassRegistry."""

    pass


class StateBackendError(Exception):
    """Raised for `StateBackend` related errors."""

    pass


class NotFoundError(StateBackendError):
    """Raised when a resource is not found."""

    pass


class NotInitialisedError(Exception):
    """Raised attempting to step or run a `Process` or `Component` that has not been initialised."""

    pass


class EventError(Exception):
    """Raised for event related errors."""

    pass


class UnrecognisedEventError(EventError):
    """Raised when an unrecognised event is encountered."""

    pass


class ValidationError(Exception):
    """Raised when an invalid `Process` or `Component` is encountered."""

    pass


class ConstraintError(Exception):
    """Raised when a constraint is violated."""

    pass


class ProcessStatusError(Exception):
    """Raised when a `Process` is in an invalid state for the requested operation."""

    pass
