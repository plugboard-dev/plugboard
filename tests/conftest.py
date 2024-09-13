"""Configuration for the test suite."""

import pytest


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Returns the name of the AnyIO backend to use."""
    return "asyncio"
