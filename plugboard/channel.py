"""Provides `Channel` base class for data communication."""

from abc import ABC, abstractmethod
import typing as _t


CHAN_MAXSIZE = 0  # Max number of items in the channel. Value <= 0 implies unlimited.


class Channel(ABC):
    """`Channel` defines an interface for data communication."""

    _maxsize = CHAN_MAXSIZE

    @property
    def maxsize(self) -> int:
        """Returns the message capacity of the `Channel`."""
        return self._maxsize

    @abstractmethod
    async def send(self, msg: _t.Any) -> None:
        """Sends an item through the `Channel`.

        Args:
            msg: The item to be sent through the `Channel`.
        """
        pass

    @abstractmethod
    async def recv(self) -> _t.Any:
        """Receives an item from the `Channel` and returns it."""
        pass
