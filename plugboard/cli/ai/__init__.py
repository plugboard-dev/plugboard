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


def _install_skills(source_dir: Path, target_dir: Path) -> tuple[list[Path], list[Path]]:
    """Install packaged skills into a style-specific skills directory.

    Creates the target directory when needed and returns the existing and created skill
    directory paths.
    Validation and source discovery are performed separately by
    `_get_skill_sources_and_validate_target`.
    """
    existing_skills, skill_sources = _get_skill_sources_and_validate_target(source_dir, target_dir)

    created_paths: list[Path] = []
    if skill_sources:
        target_dir.mkdir(parents=True, exist_ok=True)
    for skill_source in skill_sources:
        skill_target = target_dir / skill_source.name
        shutil.copytree(skill_source, skill_target)
        created_paths.append(skill_target)

    return existing_skills, created_paths


def _get_skill_sources_and_validate_target(
    source_dir: Path, target_dir: Path
) -> tuple[list[Path], list[Path]]:
    """Return packaged skill directories after validating the target directory.

    Returns the existing and missing packaged skill directory paths. Exits with status code 1 if
    the target path is invalid or if a packaged skill target exists as a non-directory path.
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
    existing_skills: list[Path] = []
    missing_skills: list[Path] = []
    invalid_targets: list[str] = []
    for skill_source in skill_sources:
        skill_target = target_dir / skill_source.name
        if skill_target.is_dir():
            existing_skills.append(skill_target)
        elif skill_target.exists():
            invalid_targets.append(skill_source.name)
        else:
            missing_skills.append(skill_source)

    if invalid_targets:
        conflicts = ", ".join(invalid_targets)
        stderr.print(
            "[red]Cannot initialise AI files[/red]: "
            f"skill targets exist and are not directories: {conflicts}."
        )
        raise typer.Exit(1)

    return existing_skills, missing_skills


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

    if agents_target.exists() and not agents_target.is_file():
        stderr.print("[red]Cannot initialise AI files[/red]: AGENTS.md exists and is not a file.")
        raise typer.Exit(1)

    existing_skills, created_skills = _install_skills(_SKILLS_DIR, skills_target)
    if agents_target.exists():
        print(f"[yellow]Exists[/yellow] {agents_target}")
    else:
        shutil.copy2(_AGENTS_MD, agents_target)
        print(f"[green]Created[/green] {agents_target}")

    if existing_skills:
        print(
            "[yellow]Existing packaged skills[/yellow] "
            + ", ".join(skill_dir.name for skill_dir in existing_skills)
        )
    print(f"[green]Added[/green] {len(created_skills)} skills to {skills_target}")
