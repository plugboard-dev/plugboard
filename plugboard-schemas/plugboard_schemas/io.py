"""Provides classes related to IO."""

from enum import StrEnum


class IODirection(StrEnum):
    """`IODirection` defines the type of IO operation.

    Attributes:
        INPUT: Specifies an input to a [`Component`][plugboard.component.Component].
        OUTPUT: Specifies an output to a [`Component`][plugboard.component.Component].
    """

    INPUT = "input"
    OUTPUT = "output"
