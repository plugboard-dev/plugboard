"""Tests that process inspection does not acquire external resources."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import msgspec
import pytest
from typer.testing import CliRunner

from plugboard.cli import app
from plugboard.component import Component, IOController as IO
from plugboard.connector import AsyncioConnector, RayConnector, ZMQConnector
from plugboard.diagram import MermaidDiagram
from plugboard.exceptions import ValidationError
from plugboard.library import FileWriter
from plugboard.process import LocalProcess, RayProcess
from plugboard.schemas import ConfigSpec, ConnectorMode, ConnectorSpec
from plugboard.state import RayStateBackend
from plugboard.utils import DI, Settings


class Source(Component):
    """A source used to describe a valid topology."""

    io = IO(outputs=["value"])

    async def step(self) -> None:
        """Produce no values; only topology metadata is used by these tests."""
        pass


class Sink(Component):
    """A sink used to describe a valid topology."""

    io = IO(inputs=["value"])

    async def step(self) -> None:
        """Consume no values; only topology metadata is used by these tests."""
        pass


def test_file_writer_inspection_does_not_touch_destination(tmp_path: Path) -> None:
    """Construction, validation, diagramming, and export leave output files untouched."""
    output_path = tmp_path / "output.csv"
    output_path.write_text("existing data\n")
    writer = FileWriter(name="writer", path=str(output_path), field_names=["value"])
    process = LocalProcess(
        components=[Source(name="source"), writer],
        connectors=[
            AsyncioConnector(spec=ConnectorSpec(source="source.value", target="writer.value"))
        ],
    )

    process.validate()
    MermaidDiagram.from_process(process)
    process.export()
    config_path = tmp_path / "process.yaml"
    process.dump(config_path)

    runner = CliRunner()
    for command in ("validate", "diagram"):
        result = runner.invoke(app, ["process", command, str(config_path)])
        assert result.exit_code == 0
        assert output_path.read_text() == "existing data\n"

    assert output_path.read_text() == "existing data\n"


@pytest.mark.asyncio
async def test_invalid_process_fails_before_initializing_writer_or_connector(
    tmp_path: Path,
) -> None:
    """Invalid topology cannot truncate files or initialize connectors."""
    output_path = tmp_path / "output.csv"
    output_path.write_text("existing data\n")
    writer = FileWriter(name="writer", path=str(output_path), field_names=["value"])
    connector = AsyncioConnector(spec=ConnectorSpec(source="source.value", target="sink.value"))
    connector.init = AsyncMock()
    process = LocalProcess(
        components=[Source(name="source"), Sink(name="sink"), writer],
        connectors=[connector],
    )

    with pytest.raises(ValidationError):
        await process.init()

    connector.init.assert_not_awaited()
    assert output_path.read_text() == "existing data\n"


def test_ray_process_inspection_does_not_create_actors(tmp_path: Path) -> None:
    """Ray process metadata can be inspected without creating any actors."""
    with (
        patch("plugboard.process.ray_process.ray.remote") as component_remote,
        patch("plugboard.connector.ray_channel.ray.remote") as channel_remote,
        patch("plugboard.state.ray_state_backend.ray.remote") as state_remote,
    ):
        process = RayProcess(
            components=[Source(name="source"), Sink(name="sink")],
            connectors=[
                RayConnector(spec=ConnectorSpec(source="source.value", target="sink.value"))
            ],
            state=RayStateBackend(),
        )

        process.validate()
        MermaidDiagram.from_process(process)
        exported = process.export()
        exported["connector_builder"] = {"type": "plugboard.connector.RayConnector"}
        config_path = tmp_path / "ray-process.yaml"
        config = ConfigSpec.model_validate({"plugboard": {"process": exported}})
        config_path.write_bytes(msgspec.yaml.encode(config.model_dump()))

        runner = CliRunner()
        for command in ("validate", "diagram"):
            result = runner.invoke(app, ["process", command, str(config_path)])
            assert result.exit_code == 0

    component_remote.assert_not_called()
    channel_remote.assert_not_called()
    state_remote.assert_not_called()


@pytest.mark.parametrize("use_proxy", [False, True])
def test_zmq_process_inspection_does_not_allocate_resources(use_proxy: bool) -> None:
    """ZMQ sockets and proxy processes are deferred until initialization."""
    settings = Settings.model_validate({"flags": {"zmq_pubsub_proxy": use_proxy}})
    with (
        DI.override_providers_sync({"settings": settings}),
        patch("plugboard.connector.zmq_channel.create_socket") as create_socket,
        patch("plugboard.utils.di.ZMQProxy") as proxy,
    ):
        process = LocalProcess(
            components=[Source(name="source"), Sink(name="sink")],
            connectors=[
                ZMQConnector(
                    spec=ConnectorSpec(
                        source="source.value",
                        target="sink.value",
                        mode=ConnectorMode.PUBSUB,
                    )
                )
            ],
        )

        process.validate()
        MermaidDiagram.from_process(process)
        process.export()

    create_socket.assert_not_called()
    proxy.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_ray_process_fails_before_creating_actors() -> None:
    """Invalid topology is rejected before process, channel, or state actors start."""
    with (
        patch("plugboard.process.ray_process.ray.remote") as component_remote,
        patch("plugboard.connector.ray_channel.ray.remote") as channel_remote,
        patch("plugboard.state.ray_state_backend.ray.remote") as state_remote,
    ):
        process = RayProcess(
            components=[Sink(name="sink")],
            connectors=[],
            state=RayStateBackend(),
        )

        with pytest.raises(ValidationError, match="unconnected inputs"):
            await process.init()

    component_remote.assert_not_called()
    channel_remote.assert_not_called()
    state_remote.assert_not_called()
