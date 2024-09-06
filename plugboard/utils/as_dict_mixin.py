"""Provides `AsDictMixin` class."""

from abc import abstractmethod


class AsDictMixin:
    """`AsDictMixin` provides functionality for converting objects to dict."""

    @abstractmethod
    def dict(self) -> dict:
        """Returns dict representation of object."""
        return {
            "__class__": self.__class__.__name__,
            "__module__": self.__module__,
        }
