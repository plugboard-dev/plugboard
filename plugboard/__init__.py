"""Plugboard is a modelling and orchestration framework for simulating complex processes."""

from importlib.metadata import version

from plugboard.utils.logging import configure_logging


__version__ = version(__package__)
configure_logging()
