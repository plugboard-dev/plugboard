"""Traffic intersection simulation components.

Simulates a dual-intersection traffic corridor where vehicles enter,
pass through Junction A, travel along a connecting road, then pass
through Junction B. Traffic lights at each junction control flow using
finite state machine (FSM) logic.

The model demonstrates event-driven simulation:
- VehicleArrivedEvent / VehicleDepartedEvent track vehicle lifecycle
- SignalChangedEvent broadcasts traffic light transitions
- CongestionAlertEvent fires when a junction queue exceeds its threshold
"""

from collections import deque
import random
import typing as _t

from pydantic import BaseModel

from plugboard.component import Component, IOController as IO
from plugboard.events import Event
from plugboard.schemas import ComponentArgsDict


# ── Event data models ───────────────────────────────────────────────────


class VehicleArrivalData(BaseModel):
    """Payload for a vehicle arrival event."""

    vehicle_id: int
    target_junction: str
    time: float


class VehicleDepartureData(BaseModel):
    """Payload for a vehicle departure event."""

    vehicle_id: int
    from_junction: str
    wait_time: float
    time: float


class SignalChangeData(BaseModel):
    """Payload for a traffic signal change event."""

    junction: str
    new_state: str
    old_state: str
    time: float


class CongestionData(BaseModel):
    """Payload for a congestion alert event."""

    junction: str
    queue_length: int
    threshold: int
    time: float


# ── Events ──────────────────────────────────────────────────────────────


class VehicleArrivedEvent(Event):
    """Emitted when a vehicle arrives at a junction queue."""

    type: _t.ClassVar[str] = "vehicle_arrived"
    data: VehicleArrivalData


class VehicleDepartedEvent(Event):
    """Emitted when a vehicle passes through a junction."""

    type: _t.ClassVar[str] = "vehicle_departed"
    data: VehicleDepartureData


class SignalChangedEvent(Event):
    """Emitted when a traffic light changes state."""

    type: _t.ClassVar[str] = "signal_changed"
    data: SignalChangeData


class CongestionAlertEvent(Event):
    """Emitted when a junction queue exceeds the congestion threshold."""

    type: _t.ClassVar[str] = "congestion_alert"
    data: CongestionData


# ── Components ──────────────────────────────────────────────────────────


class SimulationClock(Component):
    """Drives the simulation by emitting integer time steps (1 step = 1 second)."""

    io = IO(outputs=["time"])

    def __init__(
        self,
        duration: int = 600,
        **kwargs: _t.Unpack[ComponentArgsDict],
    ) -> None:
        super().__init__(**kwargs)
        self._duration: int = duration
        self._time: int = 0

    async def step(self) -> None:  # noqa: D102
        self.time = self._time
        self._time += 1
        if self._time > self._duration:
            self._logger.info("Simulation complete", duration=self._duration)
            await self.io.close()


class VehicleSource(Component):
    """Generates vehicles with Poisson arrivals.

    At each step a vehicle arrives with probability ``arrival_rate``.
    Each vehicle is assigned a unique ID and a ``VehicleArrivedEvent``
    is emitted targeting the specified junction.
    """

    io = IO(inputs=["time"], output_events=[VehicleArrivedEvent])

    def __init__(
        self,
        arrival_rate: float = 0.4,
        target_junction: str = "A",
        **kwargs: _t.Unpack[ComponentArgsDict],
    ) -> None:
        super().__init__(**kwargs)
        self._arrival_rate: float = arrival_rate
        self._target_junction: str = target_junction
        self._next_id: int = 1

    async def step(self) -> None:  # noqa: D102
        if random.random() < self._arrival_rate:  # noqa: S311
            vid = self._next_id
            self._next_id += 1
            self.io.queue_event(
                VehicleArrivedEvent(
                    source=self.name,
                    data=VehicleArrivalData(
                        vehicle_id=vid,
                        target_junction=self._target_junction,
                        time=float(self.time),
                    ),
                )
            )


class TrafficLight(Component):
    """FSM-based traffic signal controller.

    Cycles through GREEN → YELLOW → RED with configurable phase durations.
    The ``offset`` parameter shifts the starting phase so that two lights
    can be synchronised or staggered to create green-wave effects.
    A ``SignalChangedEvent`` is emitted on every state transition.
    """

    io = IO(
        inputs=["time"],
        outputs=["signal"],
        output_events=[SignalChangedEvent],
    )

    def __init__(
        self,
        junction: str = "A",
        green_duration: int = 30,
        yellow_duration: int = 5,
        red_duration: int = 30,
        offset: int = 0,
        **kwargs: _t.Unpack[ComponentArgsDict],
    ) -> None:
        super().__init__(**kwargs)
        self._junction: str = junction
        self._green: int = green_duration
        self._yellow: int = yellow_duration
        self._red: int = red_duration
        self._offset: int = offset
        self._cycle: int = green_duration + yellow_duration + red_duration
        self._signal_state: str | None = None

    def _compute_state(self, t: int) -> str:
        phase = (t + self._offset) % self._cycle
        if phase < self._green:
            return "green"
        if phase < self._green + self._yellow:
            return "yellow"
        return "red"

    async def step(self) -> None:  # noqa: D102
        t = int(self.time)
        new = self._compute_state(t)
        if new != self._signal_state:
            old = self._signal_state or "init"
            self.io.queue_event(
                SignalChangedEvent(
                    source=self.name,
                    data=SignalChangeData(
                        junction=self._junction,
                        new_state=new,
                        old_state=old,
                        time=float(t),
                    ),
                )
            )
            self._signal_state = new
        self.signal = self._signal_state


class Junction(Component):
    """FIFO vehicle queue at a signalised intersection.

    Vehicles arrive via ``VehicleArrivedEvent`` and are filtered by
    ``junction_name``.  When the signal is green, vehicles are released
    at ``service_rate`` (probability per step).  Each release produces a
    ``VehicleDepartedEvent``.  If the queue exceeds
    ``congestion_threshold`` a ``CongestionAlertEvent`` is emitted.
    """

    io = IO(
        inputs=["time", "signal"],
        outputs=["queue_length", "total_passed"],
        input_events=[VehicleArrivedEvent],
        output_events=[VehicleDepartedEvent, CongestionAlertEvent],
    )

    def __init__(
        self,
        junction_name: str = "A",
        service_rate: float = 0.8,
        capacity: int = 100,
        congestion_threshold: int = 20,
        **kwargs: _t.Unpack[ComponentArgsDict],
    ) -> None:
        super().__init__(**kwargs)
        self._junction_name: str = junction_name
        self._service_rate: float = service_rate
        self._capacity: int = capacity
        self._congestion_threshold: int = congestion_threshold
        self._queue: deque[tuple[int, float]] = deque()
        self._total_passed: int = 0
        self._congestion_active: bool = False

    @VehicleArrivedEvent.handler
    async def on_vehicle_arrived(self, event: VehicleArrivedEvent) -> None:
        """Enqueue vehicles targeted at this junction."""
        if event.data.target_junction == self._junction_name:
            if len(self._queue) < self._capacity:
                self._queue.append((event.data.vehicle_id, event.data.time))

    async def step(self) -> None:  # noqa: D102
        t = float(self.time)

        # Release one vehicle per step when green
        if self.signal == "green" and self._queue:
            if random.random() < self._service_rate:  # noqa: S311
                vehicle_id, arrival_time = self._queue.popleft()
                self._total_passed += 1
                self.io.queue_event(
                    VehicleDepartedEvent(
                        source=self.name,
                        data=VehicleDepartureData(
                            vehicle_id=vehicle_id,
                            from_junction=self._junction_name,
                            wait_time=t - arrival_time,
                            time=t,
                        ),
                    )
                )

        # Congestion detection
        qlen = len(self._queue)
        if qlen > self._congestion_threshold and not self._congestion_active:
            self._congestion_active = True
            self._logger.warning(
                "Congestion detected",
                junction=self._junction_name,
                queue_length=qlen,
            )
            self.io.queue_event(
                CongestionAlertEvent(
                    source=self.name,
                    data=CongestionData(
                        junction=self._junction_name,
                        queue_length=qlen,
                        threshold=self._congestion_threshold,
                        time=t,
                    ),
                )
            )
        elif qlen <= self._congestion_threshold:
            self._congestion_active = False

        self.queue_length = qlen
        self.total_passed = self._total_passed


class ConnectingRoad(Component):
    """Road segment between two junctions with stochastic travel time.

    Handles ``VehicleDepartedEvent`` from the upstream junction, buffers
    the vehicle for a random travel time drawn from a triangular
    distribution, then emits a ``VehicleArrivedEvent`` at the downstream
    junction.
    """

    io = IO(
        inputs=["time"],
        input_events=[VehicleDepartedEvent],
        output_events=[VehicleArrivedEvent],
    )

    def __init__(
        self,
        from_junction: str = "A",
        to_junction: str = "B",
        min_travel: float = 10.0,
        mode_travel: float = 15.0,
        max_travel: float = 25.0,
        **kwargs: _t.Unpack[ComponentArgsDict],
    ) -> None:
        super().__init__(**kwargs)
        self._from: str = from_junction
        self._to: str = to_junction
        self._min: float = min_travel
        self._mode: float = mode_travel
        self._max: float = max_travel
        self._in_transit: list[tuple[int, float]] = []

    @VehicleDepartedEvent.handler
    async def on_departed(self, event: VehicleDepartedEvent) -> None:
        """Buffer a departing vehicle with a random travel delay."""
        if event.data.from_junction == self._from:
            travel = random.triangular(self._min, self._max, self._mode)  # noqa: S311
            self._in_transit.append((event.data.vehicle_id, event.data.time + travel))

    async def step(self) -> None:  # noqa: D102
        t = float(self.time)
        remaining: list[tuple[int, float]] = []
        for vid, release in self._in_transit:
            if t >= release:
                self.io.queue_event(
                    VehicleArrivedEvent(
                        source=self.name,
                        data=VehicleArrivalData(
                            vehicle_id=vid,
                            target_junction=self._to,
                            time=t,
                        ),
                    )
                )
            else:
                remaining.append((vid, release))
        self._in_transit = remaining


class MetricsCollector(Component):
    """Subscribes to all simulation events and records them for analysis.

    After the simulation finishes, access the ``*_log`` lists and
    ``queue_history`` to build plots and compute KPIs.
    """

    io = IO(
        inputs=["time", "queue_a", "queue_b", "passed_a", "passed_b"],
        input_events=[
            VehicleArrivedEvent,
            VehicleDepartedEvent,
            CongestionAlertEvent,
            SignalChangedEvent,
        ],
    )

    def __init__(self, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)
        self.arrival_log: list[dict[str, _t.Any]] = []
        self.departure_log: list[dict[str, _t.Any]] = []
        self.congestion_log: list[dict[str, _t.Any]] = []
        self.signal_log: list[dict[str, _t.Any]] = []
        self.queue_history: list[dict[str, _t.Any]] = []

    @VehicleArrivedEvent.handler
    async def on_arrival(self, event: VehicleArrivedEvent) -> None:
        """Record vehicle arrival."""
        self.arrival_log.append(event.data.model_dump())

    @VehicleDepartedEvent.handler
    async def on_departure(self, event: VehicleDepartedEvent) -> None:
        """Record vehicle departure."""
        self.departure_log.append(event.data.model_dump())

    @CongestionAlertEvent.handler
    async def on_congestion(self, event: CongestionAlertEvent) -> None:
        """Record congestion alert."""
        self.congestion_log.append(event.data.model_dump())

    @SignalChangedEvent.handler
    async def on_signal(self, event: SignalChangedEvent) -> None:
        """Record signal change."""
        self.signal_log.append(event.data.model_dump())

    async def step(self) -> None:  # noqa: D102
        self.queue_history.append(
            {
                "time": float(self.time),
                "queue_a": int(self.queue_a),
                "queue_b": int(self.queue_b),
                "passed_a": int(self.passed_a),
                "passed_b": int(self.passed_b),
            }
        )
