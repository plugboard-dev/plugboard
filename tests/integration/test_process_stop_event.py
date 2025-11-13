"""Integration tests for gracefully stopping a running event driven Process with Components."""
# ruff: noqa: D101,D102,D103

import asyncio
import typing as _t

import pytest
import pytest_cases

from plugboard.component import Component, IOController as IO
from plugboard.connector import AsyncioConnector, Connector, ConnectorBuilder, RabbitMQConnector
from plugboard.events import EventConnectorBuilder, StopEvent
from plugboard.process import LocalProcess, Process, RayProcess
from plugboard.schemas import ConnectorSpec, Status
from tests.conftest import ComponentTestHelper, zmq_connector_cls


STOP_TOLERANCE = 3


class A(ComponentTestHelper):
    io = IO(outputs=["out_1"])

    def __init__(self, iters: int, sleep_time: float, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._iters = iters
        self._sleep_time = sleep_time

    async def init(self) -> None:
        await super().init()
        self._seq = iter(range(1, self._iters + 1))

    async def step(self) -> None:
        try:
            self.out_1 = next(self._seq)
            await asyncio.sleep(self._sleep_time)
        except StopIteration:
            await self.io.close()
        else:
            await super().step()


class B(ComponentTestHelper):
    io = IO(inputs=["in_1"])

    async def step(self) -> None:
        self.out_1 = self.in_1
        await super().step()


@pytest.mark.asyncio
@pytest_cases.parametrize(
    "process_cls, connector_cls",
    [
        (LocalProcess, AsyncioConnector),
        (LocalProcess, zmq_connector_cls),
        (LocalProcess, RabbitMQConnector),
        # (RayProcess, RayConnector),  # TODO : Pubsub/StopEvent unsupported. See https://github.com/plugboard-dev/plugboard/issues/101.
        (RayProcess, zmq_connector_cls),
        (RayProcess, RabbitMQConnector),
    ],
)
async def test_process_stop_event(
    process_cls: type[Process], connector_cls: type[Connector], ray_ctx: None
) -> None:
    connector_builder = ConnectorBuilder(connector_cls=connector_cls)
    event_connectors = EventConnectorBuilder(connector_builder=connector_builder)

    max_iters = 25
    iters_before_stop = 15
    sleep_time = 0.1

    comp_a = A(iters=max_iters, sleep_time=sleep_time, name="comp_a")
    comp_b1, comp_b2, comp_b3, comp_b4, comp_b5 = [B(name=f"comp_b{i}") for i in range(1, 6)]
    components: list[Component] = [comp_a, comp_b1, comp_b2, comp_b3, comp_b4, comp_b5]

    conn_ab1, conn_ab2, conn_ab3, conn_ab4, conn_ab5 = [
        connector_cls(spec=ConnectorSpec(source="comp_a.out_1", target=f"comp_b{i}.in_1"))
        for i in range(1, 6)
    ]
    field_connectors: list[Connector] = [conn_ab1, conn_ab2, conn_ab3, conn_ab4, conn_ab5]

    event_connectors_map = event_connectors.build(components)
    connectors: list[Connector] = list(event_connectors_map.values()) + field_connectors

    process = process_cls(components, connectors)

    async with process:
        stop_evt_conn = event_connectors_map[StopEvent.type]
        stop_chan = await stop_evt_conn.connect_send()

        async def stop_after() -> None:
            await asyncio.sleep((iters_before_stop + 0.5) * sleep_time)
            await stop_chan.send(
                StopEvent(source="test-driver", data={})  # TODO : Shouldn't need data
            )

        for c in components:
            assert c.is_initialised
            assert c.status == Status.INIT

        async with asyncio.TaskGroup() as tg:
            tg.create_task(process.run())
            tg.create_task(stop_after())

        # StopEvent is sent half way through iter n+1, where n=iters_before_stop. The event will be
        # processed by component A in the iter following this one. A does not need to wait for
        # inputs before executing step, hence the step count reaches n+2 before stopping.
        # Allow a tolerance of +/- 1
        assert comp_a.step_count == pytest.approx(iters_before_stop + 2, abs=STOP_TOLERANCE)

        # Because A sleeps for sleep_time seconds before sending outputs, the B components, which
        # block waiting for field or event inputs, will receive the StopEvent before A sends
        # the final output and then shutdown. B components cannot call step until they receive
        # inputs, and the StopEvent interrupts them before calling step, hence the count reaches n,
        for c in [comp_b1, comp_b2, comp_b3, comp_b4, comp_b5]:
            assert c.is_finished
            assert c.step_count == pytest.approx(iters_before_stop, abs=STOP_TOLERANCE)
            assert c.status == Status.STOPPED

        # A performs n+1 full steps and is interrupted on step n+2 before a final update of out_1,
        # hence n+2.
        assert comp_a.out_1 == pytest.approx(iters_before_stop + 2, abs=STOP_TOLERANCE)
        # Because the B components receive the StopEvent on iter n+1, they will only receive n
        # outputs from A before shutting down the IOController, hence n.
        for c in [comp_b1, comp_b2, comp_b3, comp_b4, comp_b5]:
            assert c.in_1 == pytest.approx(iters_before_stop, abs=STOP_TOLERANCE)
