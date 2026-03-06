"""Plugboard Go CLI - interactive AI-powered model builder."""

import typer


app = typer.Typer(rich_markup_mode="rich", pretty_exceptions_show_locals=False)


def _check_dependencies() -> None:
    """Check that optional 'go' dependencies are installed."""
    missing: list[str] = []
    try:
        import copilot  # noqa: F401
    except ImportError:
        missing.append("github-copilot")
    try:
        import textual  # noqa: F401
    except ImportError:
        missing.append("textual")
    if missing:
        typer.echo(
            f"Missing dependencies: {', '.join(missing)}\n"
            "Install them with:\n\n"
            "  pip install plugboard[go]\n"
        )
        raise typer.Exit(1)


@app.callback(invoke_without_command=True)
def go(
    model: str = typer.Option(
        "gpt-4o",
        "--model",
        "-m",
        help="LLM model to use (e.g. gpt-4o, claude-sonnet-4, gpt-5).",
    ),
) -> None:
    """Launch the interactive Plugboard model builder powered by GitHub Copilot."""
    _check_dependencies()

    from plugboard.cli.go.app import PlugboardGoApp

    tui = PlugboardGoApp(model_name=model)
    tui.run()
