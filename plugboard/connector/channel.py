"""Provides `Channel` base class for data communication."""

from abc import ABC, abstractmethod
from functools import wraps
import typing as _t

from plugboard.exceptions import ChannelClosedError
from plugboard.utils import DI


CHAN_MAXSIZE = 0  # Max number of items in the channel. Value <= 0 implies unlimited.
CHAN_CLOSE_MSG = "__PLUGBOARD_CHAN_CLOSE_MSG__"


class Channel(ABC):
    """`Channel` defines an interface for data communication."""

    _maxsize = CHAN_MAXSIZE

    def __init__(self, *args: _t.Any, maxsize: int = CHAN_MAXSIZE, **kwargs: _t.Any) -> None:  # noqa: D417
        """Initialises the `Channel`.

        Args:
            maxsize: Optional; The message capacity of the `Channel`.
        """
        self._maxsize = maxsize
        self._is_send_closed = False
        self._is_recv_closed = False
        setattr(self, "send", self._handle_send_wrapper())
        setattr(self, "recv", self._handle_recv_wrapper())
        self._logger = DI.logger.resolve_sync().bind(cls=self.__class__.__name__)
        self._logger.info("Channel created")

    @property
    def maxsize(self) -> int:
        """Returns the message capacity of the `Channel`."""
        return self._maxsize

    @property
    def is_closed(self) -> bool:
        """Returns `True` if the `Channel` is closed, `False` otherwise.

        When a `Channel` is closed, it can no longer be used to send messages,
        though there may still be some messages waiting to be read.
        """
        return self._is_send_closed

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

    async def close(self) -> None:
        """Closes the `Channel`."""
        if not self._is_send_closed:
            await self.send(CHAN_CLOSE_MSG)
            self._is_send_closed = True
            self._logger.info("Channel closed")

    def _handle_send_wrapper(self) -> _t.Callable:
        self._send = self.send

        @wraps(self.send)
        async def _wrapper(item: _t.Any) -> None:
            if self._is_send_closed:
                raise ChannelClosedError("Attempted send on closed channel.")
            await self._send(item)

        return _wrapper

    def _handle_recv_wrapper(self) -> _t.Callable:
        self._recv = self.recv

        @wraps(self.recv)
        async def _wrapper() -> _t.Any:
            if self._is_recv_closed:
                raise ChannelClosedError("Attempted recv on closed channel.")
            msg = await self._recv()
            if msg == CHAN_CLOSE_MSG:
                await self.close()
                self._is_recv_closed = True
                self._is_send_closed = True
                raise ChannelClosedError("Attempted recv on closed channel.")
            return msg

        return _wrapper
