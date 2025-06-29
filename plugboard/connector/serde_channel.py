"""Provides the `SerdeChannel` base class for serializing and deserializing messages."""

from abc import ABC, abstractmethod
from base64 import b64decode, b64encode
from functools import wraps
import pickle
import typing as _t

from plugboard.connector.channel import CHAN_CLOSE_MSG, Channel
from plugboard.exceptions import ChannelClosedError


def _serialise(item: _t.Any) -> bytes:
    """Converts item to base64-encoded pickle."""
    return b64encode(pickle.dumps(item))


def _deserialise(msg: bytes) -> _t.Any:
    """Deserialises item from base64-encoded pickle msg.

    Note: There are security implications to consider when unpickling data. It
    is assumed that data received through a channel is trusted.
    """
    return pickle.loads(b64decode(msg))  # noqa: S301 (assumed trusted data)


class SerdeChannel(Channel, ABC):
    """`SerdeChannel` base class for channels that use serialised messages."""

    @abstractmethod
    async def send(self, msg: bytes) -> None:
        """Sends an serialised message through the `Channel`.

        Args:
            msg: The message to be sent through the `Channel`.
        """
        pass

    @abstractmethod
    async def recv(self) -> bytes:
        """Receives a serialised message from the `Channel` and returns it.

        Note: Receiving data involves an unpickling deserialisation step. There are security
        implications to consider when unpickling data. It is assumed that data received through a
        channel is trusted.
        """
        pass

    def _handle_send_wrapper(self) -> _t.Callable:
        self._send = self.send

        @wraps(self.send)
        async def _wrapper(item: _t.Any) -> None:
            if self._is_send_closed:
                raise ChannelClosedError("Attempted send on closed channel.")
            await self._send(_serialise(item))

        return _wrapper

    def _handle_recv_wrapper(self) -> _t.Callable:
        self._recv = self.recv

        @wraps(self.recv)
        async def _wrapper() -> _t.Any:
            if self._is_recv_closed:
                raise ChannelClosedError("Attempted recv on closed channel.")
            msg = _deserialise(await self._recv())
            if msg == CHAN_CLOSE_MSG:
                await self.close()
                self._is_recv_closed = True
                self._is_send_closed = True
                raise ChannelClosedError("Attempted recv on closed channel.")
            return msg

        return _wrapper
