"""Placeholder hello world module for plugboard."""

from plugboard import __version__


def hello() -> None:
    """Prints a hello world message."""
    print(f"Hello, world! from version {__version__}", flush=True)
