"""Tests validation on `Process` objects."""

import pytest
from structlog.testing import capture_logs

from plugboard.process import LocalProcess
from tests.integration.test_process_with_components_run import A, C


# TODO: Update these tests when we implement full graph validation


@pytest.mark.anyio
async def test_missing_connections() -> None:
    """Tests that missing connections are logged."""
    process = LocalProcess(
        components=[A(name="a", iters=10), C(name="c", path="test-out.csv")], connectors=[]
    )
    with capture_logs():
        await process.init()

    # Must contain an error-level log indicating that input is not connected
    # TODO
