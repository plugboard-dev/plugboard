"""Plugboard Process CLI."""

import asyncio
from pathlib import Path

import msgspec
from rich import print
from rich.console import Console
import typer
from typing_extensions import Annotated

from plugboard.process import Process, ProcessBuilder
from plugboard.schemas import ConfigSpec


app = typer.Typer(rich_markup_mode="rich", no_args_is_help=True)
stderr = Console(stderr=True)


def _read_yaml(path: Path) -> ConfigSpec:
    try:
        with open(path, "rb") as f:
            data = msgspec.yaml.decode(f.read())
    except msgspec.DecodeError as e:
        stderr.print(f"[red]Invalid YAML[/red] at {path}")
        raise typer.Exit(1) from e
    return ConfigSpec.model_validate(data)


def _build_process(config: ConfigSpec) -> Process:
    process = ProcessBuilder.build(config.plugboard.process)
    return process


async def _run_process(process: Process) -> None:
    await process.init()
    await process.run()


@app.command()
def run(
    config: Annotated[
        Path,
        typer.Option(
            exists=True,
            file_okay=True,
            dir_okay=False,
            writable=False,
            readable=True,
            resolve_path=True,
            help="Path to the YAML configuration file.",
        ),
    ],
):
    """Run a Plugboard process."""
    config_spec = _read_yaml(config)
    print(f"[blue]Building process[/blue] from {config}")
    process = _build_process(config_spec)
    print(f"[blue]Running process[/blue] from {config}")
    asyncio.run(_run_process(process))
    print(f"[bold green]Process completed[/bold green]")
