"""Simple LLM example."""

# fmt: off
import asyncio
import typing as _t

import httpx
from pydantic import BaseModel

from plugboard.component import Component, IOController as IO
from plugboard.connector import AsyncioConnector

from plugboard.process import LocalProcess
from plugboard.schemas import ComponentArgsDict, ConnectorSpec
from plugboard.library import FileReader, FileWriter, LLMChat


# --8<-- [start:components]
class WeatherAPI(Component):
    """Get current weather for a location."""

    io = IO(inputs=["latitude", "longitude"], outputs=["temperature", "wind_speed"])

    def __init__(self, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)
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
        except httpx.HTTPStatusError:
            self._logger.error(
                "Error querying weather API",
                code=response.status_code,
                message=response.text,
            )
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
    connect = lambda in_, out_: AsyncioConnector(
        spec=ConnectorSpec(source=in_, target=out_)
    )
    process = LocalProcess(
        components=[load_text, llm, weather, save_output],
        connectors=[
            connect("load-text.text", "llm.prompt"),
            connect("llm.latitude", "weather.latitude"),
            connect("llm.longitude", "weather.longitude"),
            connect("llm.location", "save-results.location"),
            connect("weather.temperature", "save-results.temperature"),
            connect("weather.wind_speed", "save-results.wind_speed"),
        ],
    )
    async with process:
        await process.run()
    # --8<-- [end:main]


if __name__ == "__main__":
    asyncio.run(main())
