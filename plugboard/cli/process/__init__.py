"""Plugboard Process CLI."""

from pathlib import Path
import typing as _t

import msgspec
from rich import print
from rich.console import Console
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn
import typer
from typing_extensions import Annotated

from plugboard.diagram import MermaidDiagram
from plugboard.process import Process, ProcessBuilder
from plugboard.schemas import (
    BaseFieldSpec,
    ConfigSpec,
    override_parameter,
    parse_parameter_name,
    validate_process,
)
from plugboard.tune import Tuner
from plugboard.utils import add_sys_path, run_coro_sync


app = typer.Typer(
    rich_markup_mode="rich", no_args_is_help=True, pretty_exceptions_show_locals=False
)
stderr = Console(stderr=True)


def _read_yaml(path: Path) -> ConfigSpec:
    try:
        with open(path, "rb") as f:
            data = msgspec.yaml.decode(f.read())
    except msgspec.DecodeError as e:
        stderr.print(f"[red]Invalid YAML[/red] at {path}")
        raise typer.Exit(1) from e
    return ConfigSpec.model_validate(data)


def _parse_param_override(param: str) -> tuple[BaseFieldSpec, _t.Any]:
    """Parse a single ``name=value`` parameter override.

    Values are decoded as YAML scalars/collections so that numbers, booleans,
    nulls, lists and mappings keep their natural types. Plain strings are left
    as strings. Use quotes around a value if YAML would otherwise coerce it
    (for example ``name='"yes"'``).
    """
    if "=" not in param:
        raise typer.BadParameter(
            f"Invalid parameter override {param!r}. Expected format: name=value.",
            param_hint="--param",
        )
    key, _, raw_value = param.partition("=")
    if not key:
        raise typer.BadParameter(
            f"Invalid parameter override {param!r}. Parameter name must not be empty.",
            param_hint="--param",
        )
    if raw_value == "":
        value = ""
    else:
        try:
            value = msgspec.yaml.decode(raw_value.encode())
        except msgspec.DecodeError as e:
            raise typer.BadParameter(
                f"Could not parse value for parameter {key!r}: {raw_value!r}.",
                param_hint="--param",
            ) from e
    try:
        field = parse_parameter_name(key)
    except ValueError as e:
        raise typer.BadParameter(
            f"Invalid parameter name {key!r}: {e}",
            param_hint="--param",
        ) from e
    return field, value


def _apply_param_overrides(config: ConfigSpec, params: list[str] | None) -> None:
    """Apply CLI parameter overrides to the process configuration in place."""
    if not params:
        return
    for param in params:
        field, value = _parse_param_override(param)
        try:
            override_parameter(config.plugboard.process, field, value)
        except ValueError as e:
            raise typer.BadParameter(
                f"Invalid parameter override {param!r}: {e}", param_hint="--param"
            ) from e


def _build_process(config: ConfigSpec) -> Process:
    process = ProcessBuilder.build(config.plugboard.process)
    return process


def _build_tuner(config: ConfigSpec) -> Tuner:
    tune_config = config.plugboard.tune
    if tune_config is None:
        stderr.print("[red]No tuning configuration found in YAML file[/red]")
        raise typer.Exit(1)
    return Tuner(
        objective=tune_config.args.objective,
        parameters=tune_config.args.parameters,
        num_samples=tune_config.args.num_samples,
        mode=tune_config.args.mode,
        max_concurrent=tune_config.args.max_concurrent,
        algorithm=tune_config.args.algorithm,
    )


async def _run_process(process: Process) -> None:
    async with process:
        await process.run()


def _run_tune(tuner: Tuner, config_spec: ConfigSpec) -> None:
    process_spec = config_spec.plugboard.process
    # Build the process to import the component types
    _build_process(config_spec)
    result = tuner.run(spec=process_spec)
    print("[green]Best parameters found:[/green]")
    if isinstance(result, list):
        for r in result:
            print(f"Config: {r.config} - Metrics: {r.metrics}")
    else:
        print(f"Config: {result.config} - Metrics: {result.metrics}")


@app.command()
def run(
    config: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            writable=False,
            readable=True,
            resolve_path=True,
            help="Path to the YAML configuration file.",
        ),
    ],
    job_id: Annotated[
        _t.Optional[str],
        typer.Option(
            help="Job ID for the process. If not provided, a random job ID will be generated.",
        ),
    ] = None,
    process_type: Annotated[
        _t.Optional[_t.Literal["local", "ray"]],
        typer.Option(
            "--process-type",
            help=(
                "Override the process type. "
                "Options: 'local' for LocalProcess, 'ray' for RayProcess."
            ),
        ),
    ] = None,
    param: Annotated[
        _t.Optional[list[str]],
        typer.Option(
            "--param",
            "-p",
            help=(
                "Override a process or component field as name=value. Repeatable. "
                "Use component.<name>.<arg|initial_value|parameter>.<field> or "
                "process.default.parameter.<field>; a bare name targets a process parameter. "
                "Values are parsed as YAML."
            ),
        ),
    ] = None,
) -> None:
    """Run a Plugboard process."""
    config_spec = _read_yaml(config)

    if job_id is not None:
        # Override job ID in config file if set
        config_spec.plugboard.process.args.state.args.job_id = job_id

    if process_type is not None:
        # Use the ProcessSpec method to override the process type
        config_spec.plugboard.process = config_spec.plugboard.process.override_process_type(
            process_type  # type: ignore[arg-type]
        )

    try:
        _apply_param_overrides(config_spec, param)
    except typer.BadParameter as e:
        stderr.print(f"[red]{e}[/red]")
        raise typer.Exit(2) from e

    with Progress(
        SpinnerColumn("arrow3"),
        TextColumn("[progress.description]{task.description}"),
    ) as progress:
        task = progress.add_task(f"Building process from {config}", total=None)
        with add_sys_path(config.parent):
            process = _build_process(config_spec)
        progress.update(task, description="Running process...")
        run_coro_sync(_run_process(process))
        progress.update(task, description="[green]Process complete[/green]")


@app.command()
def tune(
    config: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            writable=False,
            readable=True,
            resolve_path=True,
            help="Path to the YAML configuration file.",
        ),
    ],
) -> None:
    """Optimise a Plugboard process by adjusting its tunable parameters."""
    config_spec = _read_yaml(config)
    with add_sys_path(config.parent):
        tuner = _build_tuner(config_spec)

    with Progress(
        SpinnerColumn("arrow3"),
        TextColumn("[progress.description]{task.description}"),
    ) as progress:
        task = progress.add_task(f"Running tune job from {config}", total=None)
        with add_sys_path(config.parent):
            _run_tune(tuner, config_spec)
        progress.update(task, description="[green]Tune job complete[/green]")


@app.command()
def diagram(
    config: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            writable=False,
            readable=True,
            resolve_path=True,
            help="Path to the YAML configuration file.",
        ),
    ],
) -> None:
    """Create a diagram of a Plugboard process."""
    config_spec = _read_yaml(config)
    with add_sys_path(config.parent):
        process = _build_process(config_spec)
    diagram = MermaidDiagram.from_process(process)
    md = Markdown(f"```\n{diagram.diagram}\n```\n[Editable diagram]({diagram.url}) (external link)")
    print(md)


@app.command()
def validate(
    config: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            writable=False,
            readable=True,
            resolve_path=True,
            help="Path to the YAML configuration file.",
        ),
    ],
) -> None:
    """Validate a Plugboard process configuration."""
    config_spec = _read_yaml(config)
    with add_sys_path(config.parent):
        process = _build_process(config_spec)
    errors = validate_process(process.dict())
    if errors:
        stderr.print("[red]Validation failed:[/red]")
        for error in errors:
            stderr.print(f"  • {error}")
        raise typer.Exit(1)
    print("[green]Validation passed[/green]")
