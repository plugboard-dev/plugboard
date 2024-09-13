"""Provides classes related to IO."""

from enum import StrEnum


class IODirection(StrEnum):
    """`IODirection` defines the type of IO operation."""

    INPUT = "input"
    OUTPUT = "output"
