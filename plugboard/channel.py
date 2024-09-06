"""Provides `Channel` base class for data communication."""

from abc import ABC, abstractmethod
import typing as _t

from plugboard.utils import AsDictMixin


CHAN_MAXSIZE = 0  # Max number of items in the channel. Value <= 0 implies unlimited.


class Channel(ABC, AsDictMixin):
    """`Channel` defines an interface for data communication."""

    _maxsize = CHAN_MAXSIZE

    @property
    def maxsize(self) -> int:
        """Returns the message capacity of the `Channel`."""
        return self._maxsize

    def __init__(self, ref: str, *args: _t.Any, **kwargs: _t.Any) -> None:
        """Initializes the `Channel` with a reference and optional arguments."""
        self._ref = ref
        super().__init__(*args, **kwargs)  # type: ignore

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

    def dict(self) -> dict[str, _t.Any]:  # noqa: D102
        return {
            **super().dict(),
            "ref": self._ref,
            "maxsize": self._maxsize,
        }
