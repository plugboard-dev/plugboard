"""Tests validation on `Process` objects."""

import re
import typing as _t

import pytest
from structlog.testing import capture_logs

from plugboard import exceptions
from plugboard.component import Component, IOController as IO
from plugboard.process import LocalProcess
from tests.integration.test_process_with_components_run import A, C


# TODO: Update these tests when we implement full graph validation


def filter_logs(logs: list[dict], field: str, regex: str) -> list[dict]:
    """Filters the log output by applying regex to a field."""
    pattern = re.compile(regex)
    return [l for l in logs if pattern.match(l[field])]


@pytest.mark.anyio
async def test_missing_connections() -> None:
    """Tests that missing connections are logged."""
    process = LocalProcess(
        components=[A(name="a", iters=10), C(name="c", path="test-out.csv")], connectors=[]
    )
    with capture_logs() as logs:
        await process.init()

    # Must contain an error-level log indicating that input is not connected
    logs = filter_logs(logs, "level", "error")
    logs = filter_logs(logs, "event", "input not connected")
    assert logs, "Logs do not indicate missing connection"


@pytest.mark.anyio
async def test_component_validation() -> None:
    """Tests that invalid components are detected."""

    class NoSuperCall(Component):
        io = IO(inputs=["x"], outputs=["y"])

        def __init__(*args: _t.Any, **kwargs: _t.Any):
            pass

        async def step(self) -> None:
            self.y = self.x

    process = LocalProcess(
        components=[A(name="a", iters=10), NoSuperCall(name="test-no-super")], connectors=[]
    )

    with pytest.raises(exceptions.ComponentValidationError):
        await process.init()
