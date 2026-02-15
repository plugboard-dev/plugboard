"""Plugboard CLI."""

import typer

from plugboard import __version__
from plugboard.cli.process import app as process_app
from plugboard.cli.server import app as server_app
from plugboard.cli.version import app as version_app


app = typer.Typer(
    rich_markup_mode="rich",
    no_args_is_help=True,
    help=f"[bold]Plugboard CLI[/bold]\n\nVersion {__version__}",
    pretty_exceptions_show_locals=False,
)
app.add_typer(process_app, name="process")
app.add_typer(server_app, name="server")
app.add_typer(version_app, name="version")
