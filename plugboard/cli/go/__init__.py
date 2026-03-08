"""Plugboard Go CLI - interactive AI-powered model builder."""

import typer

from plugboard.utils.dependencies import depends_on_optional


app = typer.Typer(rich_markup_mode="rich", pretty_exceptions_show_locals=False)


@depends_on_optional("textual", extra="go")
@depends_on_optional("copilot", extra="go")
def _run_go(model: str) -> None:
    """Launch the Plugboard Go TUI."""
    from plugboard.cli.go.app import PlugboardGoApp

    tui = PlugboardGoApp(model_name=model)
    tui.run()


@app.callback(invoke_without_command=True)
def go(
    model: str = typer.Option(
        "gpt-5-mini",
        "--model",
        "-m",
        help="LLM model to use (e.g. gpt-5-mini, claude-sonnet-4, gpt-5.4).",
    ),
) -> None:
    """Launch the interactive Plugboard model builder powered by GitHub Copilot."""
    try:
        _run_go(model)
    except ImportError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
