"""Plugboard AI CLI."""

from pathlib import Path
import shutil

from rich import print
from rich.console import Console
import typer


app = typer.Typer(
    rich_markup_mode="rich", no_args_is_help=True, pretty_exceptions_show_locals=False
)
stderr = Console(stderr=True)

_AGENTS_MD = Path(__file__).parent / "AGENTS.md"


@app.command()
def init(
    directory: Path = typer.Argument(
        default=None,
        help="Target directory for the AGENTS.md file. Defaults to the current working directory.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
) -> None:
    """Initialise a project with an AGENTS.md file for AI-assisted development."""
    if directory is None:
        directory = Path.cwd()

    target = directory / "AGENTS.md"

    if target.exists():
        stderr.print("[red]AGENTS.md already exists[/red] in the target directory.")
        raise typer.Exit(1)

    shutil.copy2(_AGENTS_MD, target)
    print(f"[green]Created[/green] {target}")
