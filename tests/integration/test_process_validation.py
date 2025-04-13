"""Tests validation on `Process` objects."""

import re
import typing as _t

import pytest
from structlog.testing import capture_logs
from structlog.typing import EventDict

from plugboard import exceptions
from plugboard.component import Component, IOController as IO
from plugboard.connector import AsyncioConnector
from plugboard.process import LocalProcess
from plugboard.schemas import ConnectorSpec
from tests.integration.test_process_with_components_run import A, B, C


# TODO: Update these tests when we implement full graph validation


def filter_logs(logs: list[EventDict], field: str, regex: str) -> list[EventDict]:
    """Filters the log output by applying regex to a field."""
    pattern = re.compile(regex)
    return [l for l in logs if pattern.match(l[field])]


@pytest.mark.asyncio
async def test_missing_connections() -> None:
    """Tests that missing connections are logged."""
    p_missing_input = LocalProcess(
        components=[A(name="a", iters=10), C(name="c", path="test-out.csv")],
        # c.in_1 is not connected
        connectors=[AsyncioConnector(spec=ConnectorSpec(source="a.out_1", target="unknown.x"))],
    )
    with capture_logs() as logs:
        await p_missing_input.init()

    # Must contain an error-level log indicating that input is not connected
    logs = filter_logs(logs, "log_level", "error")
    logs = filter_logs(logs, "event", "Input fields not connected")
    assert logs, "Logs do not indicate missing connection"

    p_missing_output = LocalProcess(
        components=[A(name="a", iters=10), B(name="b")],
        # b.out_1 is not connected
        connectors=[AsyncioConnector(spec=ConnectorSpec(source="a.out_1", target="b.in_1"))],
    )
    with capture_logs() as logs:
        await p_missing_output.init()

    # Must contain an warning-level log indicating that output is not connected
    logs = filter_logs(logs, "log_level", "warning")
    logs = filter_logs(logs, "event", "Output fields not connected")
    assert logs, "Logs do not indicate missing connection"

    p_fully_connected = LocalProcess(
        components=[A(name="a", iters=10), C(name="c", path="test-out.csv")],
        connectors=[AsyncioConnector(spec=ConnectorSpec(source="a.out_1", target="c.in_1"))],
    )
    with capture_logs() as logs:
        await p_fully_connected.init()

    # No missing connections, so no errors/warnings should be logged
    logs = filter_logs(logs, "event", "not connected")
    assert not logs, "Logs indicate missing connection"


@pytest.mark.asyncio
async def test_component_validation() -> None:
    """Tests that invalid components are detected."""

    class NoSuperCall(Component):
        io = IO(inputs=["x"], outputs=["y"])

        def __init__(*args: _t.Any, **kwargs: _t.Any):
            pass

        async def step(self) -> None:
            self.y = self.x

    process = LocalProcess(
        components=[A(name="a", iters=10), NoSuperCall(name="test-no-super")],
        connectors=[
            AsyncioConnector(spec=ConnectorSpec(source="a.out_1", target="test-no-super.x"))
        ],
    )

    with pytest.raises(ExceptionGroup) as exc_info:
        await process.init()

    assert exc_info.group_contains(exceptions.ValidationError), "No ValidationError raised"
