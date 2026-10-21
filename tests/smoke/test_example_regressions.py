"""Regression checks for tutorial data flow, tuning, and HTTP resource ownership."""

import asyncio
import csv
import importlib
import math
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import httpx2
from optuna.trial import FixedTrial
import pytest

from plugboard.cli.process import _build_tuner, _read_yaml
from plugboard.connector import AsyncioConnector
from plugboard.library import FileWriter
from plugboard.process import LocalProcess, ProcessBuilder
from plugboard.schemas import ConnectorSpec, ProcessSpec


TUTORIALS = Path(__file__).resolve().parents[2] / "examples/tutorials"
pytestmark = pytest.mark.smoke


def tutorial(monkeypatch: pytest.MonkeyPatch, folder: str, module: str) -> ModuleType:
    """Import tutorial classes without executing their script entrypoint."""
    monkeypatch.syspath_prepend(str(TUTORIALS / folder))
    return importlib.import_module(module)


async def test_ray_iterator_sequence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Assert the actual values reaching a downstream component, including zero."""
    module = tutorial(monkeypatch, "004_using_ray", "hello_ray")
    output = tmp_path / "sequence.csv"
    process = LocalProcess(
        components=[
            module.Iterator(name="source", iters=5),
            FileWriter(name="sink", path=str(output), field_names=["value"]),
        ],
        connectors=[AsyncioConnector(spec=ConnectorSpec(source="source.x", target="sink.value"))],
    )
    async with process:
        await asyncio.wait_for(process.run(), timeout=10)
    with output.open() as stream:
        assert [int(row["value"]) for row in csv.DictReader(stream)] == list(range(5))


def test_custom_trial_reaches_trajectory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the tuner's real objective with two fixed suggestions and inspect components."""
    module = tutorial(monkeypatch, "006_optimisation", "hello_tuner")
    config = _read_yaml(TUTORIALS / "006_optimisation/model-with-tuner-custom.yaml")
    tuner = _build_tuner(config)
    spec = config.plugboard.process
    build = ProcessBuilder.build
    built: list[LocalProcess] = []

    def capture(spec: ProcessSpec) -> LocalProcess:
        process = build(spec)
        assert isinstance(process, LocalProcess)
        built.append(process)
        return process

    objective = tuner._build_objective({}, spec)
    metrics = []
    for angle, velocity in [(20, 40), (60, 80)]:
        trial = FixedTrial(
            {"component.trajectory.arg.angle": angle, "component.trajectory.arg.velocity": velocity}
        )
        module.custom_space(trial)
        with patch.object(ProcessBuilder, "build", side_effect=capture):
            result = objective(trial.params)
        trajectory = built[-1].components["trajectory"]
        assert trajectory._angle_radians == pytest.approx(math.radians(angle))
        assert trajectory._v0 == velocity
        expected = max(
            x * math.tan(math.radians(angle))
            - 9.81 * x**2 / (2 * velocity**2 * math.cos(math.radians(angle)) ** 2)
            for x in range(100)
        )
        metric = result["component.max-height.field.max_y"]
        assert metric == pytest.approx(expected)
        metrics.append(metric)
    assert metrics[0] != metrics[1]


@pytest.mark.parametrize("failure", ["status", "transport"])
async def test_weather_failure_and_cleanup(monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    """A failure following success emits fresh missing values and closes the owned client."""
    module = tutorial(monkeypatch, "003_more_components", "hello_llm")
    calls = 0

    def respond(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx2.Response(
                200, json={"current": {"temperature_2m": 18, "wind_speed_10m": 3}}
            )
        if failure == "transport":
            raise httpx2.ConnectError("offline", request=request)
        return httpx2.Response(503, text="Unavailable")

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(respond))
    with patch.object(module.httpx2, "AsyncClient", return_value=client):
        weather = module.WeatherAPI(name="weather")
    try:
        await weather.init()
        weather.latitude, weather.longitude = 51.5, -0.1
        await weather.step()
        assert (weather.temperature, weather.wind_speed) == (18, 3)
        weather.latitude, weather.longitude = 40, -74
        await weather.step()
        assert (weather.temperature, weather.wind_speed) == (None, None)
    finally:
        await weather.destroy()
    assert client.is_closed
