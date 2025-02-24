"""Simple hello world example."""

# fmt: off
import asyncio
import typing as _t

import httpx
from pydantic import BaseModel

from plugboard.component import Component, IOController as IO
from plugboard.connector import AsyncioConnector

from plugboard.process import LocalProcess
from plugboard.schemas import ConnectorSpec
from plugboard.library import FileReader, FileWriter, LLMChat


# --8<-- [start:components]
class WeatherAPI(Component):
    """Get current weather for a location."""

    io = IO(inputs=["latitude", "longitude"], outputs=["temperature", "wind_speed"])

    def __init__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._client = httpx.AsyncClient()

    async def step(self) -> None:
        response = await self._client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": self.latitude,
                "longitude": self.longitude,
                "current": "temperature_2m,wind_speed_10m",
            },
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            print(f"Error querying weather API: {e}")
            return
        data = response.json()
        self.temperature = data["current"]["temperature_2m"]
        self.wind_speed = data["current"]["wind_speed_10m"]
# --8<-- [end:components]


# --8<-- [start:response_structure]
class Location(BaseModel):  # (1)!
    location: str
    latitude: float
    longitude: float
# --8<-- [end:response_structure]


async def main() -> None:
    # --8<-- [start:load-save]
    load_text = FileReader(name="load-text", path="input.csv", field_names=["text"])
    save_output = FileWriter(
        name="save-results",
        path="output.csv",
        field_names=["location", "temperature", "wind_speed"],
    )
    # --8<-- [end:load-save]
    # --8<-- [start:llm]
    llm = LLMChat(
        name="llm",
        system_prompt="Identify a geographical location from the input and provide its latitude and longitude",
        response_model=Location,
        expand_response=True,  # (2)!
    )
    # --8<-- [end:llm]
    # --8<-- [start:weather]
    weather = WeatherAPI(name="weather")
    # --8<-- [end:weather]
    # --8<-- [start:main]
    process = LocalProcess(
        components=[load_text, llm, weather, save_output],
        connectors=[
            AsyncioConnector(spec=ConnectorSpec(source="load-text.text", target="llm.prompt")),
            AsyncioConnector(spec=ConnectorSpec(source="llm.latitude", target="weather.latitude")),
            AsyncioConnector(
                spec=ConnectorSpec(source="llm.longitude", target="weather.longitude")
            ),
            AsyncioConnector(
                spec=ConnectorSpec(source="llm.location", target="save-results.location")
            ),
            AsyncioConnector(
                spec=ConnectorSpec(source="weather.temperature", target="save-results.temperature")
            ),
            AsyncioConnector(
                spec=ConnectorSpec(source="weather.wind_speed", target="save-results.wind_speed")
            ),
        ],
    )
    async with process:
        await process.run()
    # --8<-- [end:main]


if __name__ == "__main__":
    asyncio.run(main())
