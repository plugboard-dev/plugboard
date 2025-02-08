"""Plugboard Process CLI."""

import asyncio
from pathlib import Path

import msgspec
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
import typer
from typing_extensions import Annotated

from plugboard.process import Process, ProcessBuilder
from plugboard.schemas import ConfigSpec
from plugboard.utils import add_sys_path


app = typer.Typer(
    rich_markup_mode="rich", no_args_is_help=True, pretty_exceptions_show_locals=False
)
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
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            writable=False,
            readable=True,
            resolve_path=True,
            help="Path to the YAML configuration file.",
        ),
    ],
) -> None:
    """Run a Plugboard process."""
    config_spec = _read_yaml(config)

    with Progress(
        SpinnerColumn("arrow3"),
        TextColumn("[progress.description]{task.description}"),
    ) as progress:
        task = progress.add_task(f"Building process from {config}", total=None)
        with add_sys_path(config.parent):
            process = _build_process(config_spec)
        progress.update(task, description=f"Running process...")
        asyncio.run(_run_process(process))
        progress.update(task, description=f"[green]Process complete[/green]")
