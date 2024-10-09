"""Plugboard Process CLI."""

from pathlib import Path

import typer
from typing_extensions import Annotated


app = typer.Typer(rich_markup_mode="rich", no_args_is_help=True)


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
    print("Running the process.")
