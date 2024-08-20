"""Tests for the placeholder hello module."""

import typing as _t

from plugboard import __version__, hello


def test_hello(capfd: _t.Any) -> None:
    """Tests the hello function."""
    hello.hello()
    out, _ = capfd.readouterr()
    assert out == f"Hello, world! from version {__version__}\n"
