"""Plugboard CLI."""

import typer

from plugboard import __version__
from plugboard.cli.process import app as process_app


app = typer.Typer(
    rich_markup_mode="rich",
    no_args_is_help=True,
    help=f"[bold]Plugboard CLI[/bold]\n\nVersion {__version__}",
    pretty_exceptions_show_locals=False,
)
app.add_typer(process_app, name="process")
