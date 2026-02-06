"""Plugboard Version CLI."""

import platform
import sys

import typer

from plugboard import __version__


app = typer.Typer(
    rich_markup_mode="rich", pretty_exceptions_show_locals=False
)


@app.callback(invoke_without_command=True)
def version() -> None:
    """Display version and system information."""
    python_version = sys.version.split()[0]
    platform_info = platform.platform()

    typer.echo(f"Plugboard version: {__version__}")
    typer.echo(f"Platform: {platform_info}")
    typer.echo(f"Python version: {python_version}")
