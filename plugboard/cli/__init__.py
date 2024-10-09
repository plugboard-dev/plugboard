"""Plugboard CLI."""

import typer

from plugboard.cli.process import app as process_app


app = typer.Typer(no_args_is_help=True)
app.add_typer(process_app, name="process")

if __name__ == "__main__":
    app()
