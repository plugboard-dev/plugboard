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
_SKILLS_DIR = Path(__file__).parent / "skills"


@app.command()
def init(
    directory: Path = typer.Argument(
        default=None,
        help=(
            "Target directory for the AGENTS.md file and skills directory. "
            "Defaults to the current working directory."
        ),
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
) -> None:
    """Initialise a project with Plugboard AI guidance files."""
    if directory is None:
        directory = Path.cwd()

    agents_target = directory / "AGENTS.md"
    skills_target = directory / "skills"
    conflicts = [path.name for path in (agents_target, skills_target) if path.exists()]

    if conflicts:
        existing = ", ".join(conflicts)
        stderr.print(
            "[red]Cannot initialise AI files[/red]: "
            f"{existing} already exists in the target directory."
        )
        raise typer.Exit(1)

    shutil.copy2(_AGENTS_MD, agents_target)
    shutil.copytree(_SKILLS_DIR, skills_target)
    print(f"[green]Created[/green] {agents_target}")
    print(f"[green]Created[/green] {skills_target}")
