"""Plugboard is a modelling and orchestration framework for simulating complex processes."""

from importlib.metadata import version


_PACKAGE_NAME = __package__ or __name__.split(".")[0]


__version__ = version(_PACKAGE_NAME)
