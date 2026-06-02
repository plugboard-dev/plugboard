"""Plugboard AI CLI."""

from pathlib import Path
import shutil
import typing as _t

from rich import print
from rich.console import Console
import typer


app = typer.Typer(
    rich_markup_mode="rich", no_args_is_help=True, pretty_exceptions_show_locals=False
)
stderr = Console(stderr=True)

_AGENTS_MD = Path(__file__).parent / "AGENTS.md"
_SKILLS_DIR = Path(__file__).parent / "skills"
_STYLE_SKILLS_DIRS: dict[str, Path] = {
    "agents": Path(".agents/skills"),
    "github": Path(".github/skills"),
    "claude": Path(".claude/skills"),
}


def _install_skills(source_dir: Path, target_dir: Path) -> list[Path]:
    """Install packaged skills into a style-specific skills directory.

    Creates the target directory when needed and returns the created skill directory paths.
    Validation and source discovery are performed separately by
    `_get_skill_sources_and_validate_target`.
    """
    skill_sources = _get_skill_sources_and_validate_target(source_dir, target_dir)

    target_dir.mkdir(parents=True, exist_ok=True)
    created_paths: list[Path] = []
    for skill_source in skill_sources:
        skill_target = target_dir / skill_source.name
        shutil.copytree(skill_source, skill_target)
        created_paths.append(skill_target)

    return created_paths


def _get_skill_sources_and_validate_target(source_dir: Path, target_dir: Path) -> list[Path]:
    """Return packaged skill directories after validating the target directory.

    Returns the packaged skill source directories. Exits with status code 1 if the target path
    is invalid or if packaged Plugboard skill directories already exist in the target.
    """
    if not source_dir.is_dir():
        stderr.print(
            "[red]Cannot initialise AI files[/red]: "
            f"packaged skills directory is missing: {source_dir}."
        )
        raise typer.Exit(1)

    if target_dir.exists() and not target_dir.is_dir():
        stderr.print(
            "[red]Cannot initialise AI files[/red]: "
            f"{target_dir.name} exists and is not a directory."
        )
        raise typer.Exit(1)

    skill_sources = sorted(path for path in source_dir.iterdir() if path.is_dir())
    existing_skill_names: set[str] = set()
    if target_dir.exists():
        existing_skill_names = {path.name for path in target_dir.iterdir() if path.is_dir()}
    conflicting_skills = [path.name for path in skill_sources if path.name in existing_skill_names]
    if conflicting_skills:
        conflicts = ", ".join(conflicting_skills)
        stderr.print(
            f"[red]Cannot initialise AI files[/red]: skill directories already exist: {conflicts}."
        )
        raise typer.Exit(1)

    return skill_sources


@app.command()
def init(
    directory: Path = typer.Argument(
        default=None,
        help=(
            "Target directory for the AGENTS.md file and style-specific skills directory. "
            "Defaults to the current working directory."
        ),
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    style: _t.Annotated[
        _t.Literal["claude", "github", "agents"],
        typer.Option(
            "--style",
            help=(
                "Skill installation style. "
                "Options: 'agents' for .agents/skills, "
                "'github' for .github/skills, "
                "'claude' for .claude/skills."
            ),
        ),
    ] = "agents",
) -> None:
    """Initialise a project with Plugboard AI guidance files."""
    if directory is None:
        directory = Path.cwd()

    agents_target = directory / "AGENTS.md"
    skills_target = directory / _STYLE_SKILLS_DIRS[style]

    if agents_target.exists():
        stderr.print("[red]Cannot initialise AI files[/red]: AGENTS.md already exists.")
        raise typer.Exit(1)

    _get_skill_sources_and_validate_target(_SKILLS_DIR, skills_target)
    shutil.copy2(_AGENTS_MD, agents_target)
    created_skills = _install_skills(_SKILLS_DIR, skills_target)
    print(f"[green]Created[/green] {agents_target}")
    print(f"[green]Added[/green] {len(created_skills)} skills to {skills_target}")
