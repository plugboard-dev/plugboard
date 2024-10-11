"""Plugboard CLI."""

import typer

from plugboard import __version__
from plugboard.cli.process import app as process_app


app = typer.Typer(
    rich_markup_mode="rich",
    no_args_is_help=True,
    help=f"[bold]Plugboard CLI[/bold]\n\nVersion {__version__}",
)
app.add_typer(process_app, name="process")

if __name__ == "__main__":
    app()
