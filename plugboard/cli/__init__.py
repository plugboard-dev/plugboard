"""Plugboard CLI."""

import platform
import sys

import typer

from plugboard import __version__
from plugboard.cli.process import app as process_app
from plugboard.cli.server import app as server_app


app = typer.Typer(
    rich_markup_mode="rich",
    no_args_is_help=True,
    help=f"[bold]Plugboard CLI[/bold]\n\nVersion {__version__}",
    pretty_exceptions_show_locals=False,
)
app.add_typer(process_app, name="process")
app.add_typer(server_app, name="server")


@app.command()
def version() -> None:
    """Display version and system information."""
    python_version = sys.version.split()[0]
    platform_info = platform.platform()
    
    typer.echo(f"Plugboard version: {__version__}")
    typer.echo(f"Platform: {platform_info}")
    typer.echo(f"Python version: {python_version}")
