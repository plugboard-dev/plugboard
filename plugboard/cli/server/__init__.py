"""Plugboard Server CLI."""

import importlib
import inspect
import json
import logging
import os
from pathlib import Path
import sys
import typing as _t
import urllib.request

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
import typer
from typing_extensions import Annotated


app = typer.Typer(
    rich_markup_mode="rich", no_args_is_help=True, pretty_exceptions_show_locals=False
)
stderr = Console(stderr=True)
logger = logging.getLogger(__name__)


def _post_to_api(url: str, data: dict) -> None:
    """Post data to the given API URL."""
    req = urllib.request.Request(  # noqa: S310
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as response:  # noqa: S310
            if response.status not in (200, 201):
                logger.error(
                    f"Failed to post to {url}: {response.status} {response.read().decode()}"
                )
            else:
                logger.debug(f"Successfully posted to {url}")
    except Exception as e:
        logger.error(f"Error posting to {url}: {e}")


def _import_recursive(path: Path, base_package: _t.Optional[str] = None) -> None:
    """Import all modules recursively from the given path."""
    for root, _dirs, files in os.walk(path):
        for file in files:
            if file.endswith(".py") and not file.startswith("__"):
                # Construct module name
                rel_path = os.path.relpath(os.path.join(root, file), path)
                module_name = rel_path.replace(os.sep, ".")[:-3]

                if base_package:
                    module_name = f"{base_package}.{module_name}"

                try:
                    importlib.import_module(module_name)
                except Exception as e:
                    logger.warning(f"Failed to import module {module_name}: {e}")


def _get_all_subclasses(cls: type) -> set:
    """Recursively get all subclasses of a given class."""
    return set(cls.__subclasses__()).union(
        [s for c in cls.__subclasses__() for s in _get_all_subclasses(c)]
    )


def _get_docstring(cls: type) -> _t.Optional[str]:
    """Get the docstring of a class."""
    return inspect.getdoc(cls)


def _discover_components(api_url: str, base_cls: type) -> None:
    """Discover and register all Component subclasses."""
    components = [c for c in _get_all_subclasses(base_cls) if not inspect.isabstract(c)]
    logger.info(f"Found {len(components)} components")
    for c in components:
        logger.info(f"Registering component: {c.__name__}")

        io = getattr(c, "io", None)
        inputs = []
        outputs = []
        input_events = []
        output_events = []

        if io:
            inputs = list(io.inputs)
            outputs = list(io.outputs)
            input_events = [getattr(e, "type", str(e)) for e in io.input_events]
            output_events = [getattr(e, "type", str(e)) for e in io.output_events]

        data = {
            "id": f"{c.__module__}.{c.__qualname__}",
            "name": c.__name__,
            "description": _get_docstring(c),
            "args_schema": {},  # Placeholder
            "inputs": inputs,
            "outputs": outputs,
            "input_events": input_events,
            "output_events": output_events,
        }
        _post_to_api(f"{api_url}/types/component", data)


def _discover_connectors(api_url: str, base_cls: type) -> None:
    """Discover and register all Connector subclasses."""
    connectors = [c for c in _get_all_subclasses(base_cls) if not inspect.isabstract(c)]
    logger.info(f"Found {len(connectors)} connectors")
    for c in connectors:
        logger.info(f"Registering connector: {c.__name__}")
        data = {
            "id": f"{c.__module__}.{c.__qualname__}",
            "name": c.__name__,
            "description": _get_docstring(c),
            "parameters_schema": {},  # Placeholder
        }
        _post_to_api(f"{api_url}/types/connector", data)


def _discover_events(api_url: str, base_cls: type) -> None:
    """Discover and register all Event subclasses."""
    events = [
        c
        for c in _get_all_subclasses(base_cls)
        if not inspect.isabstract(c) and c.__name__ != "SystemEvent"
    ]
    logger.info(f"Found {len(events)} events")
    for c in events:
        logger.info(f"Registering event: {c.__name__}")
        schema = {}
        if hasattr(c, "model_json_schema"):
            schema = c.model_json_schema()

        data = {
            "type": getattr(c, "type", c.__name__),
            "description": _get_docstring(c),
            "schema": schema,
        }
        _post_to_api(f"{api_url}/types/event", data)


def _discover_processes(api_url: str, base_cls: type) -> None:
    """Discover and register all Process subclasses."""
    processes = [c for c in _get_all_subclasses(base_cls) if not inspect.isabstract(c)]
    logger.info(f"Found {len(processes)} processes")
    for c in processes:
        logger.info(f"Registering process: {c.__name__}")
        data = {
            "id": f"{c.__module__}.{c.__qualname__}",
            "name": c.__name__,
            "description": _get_docstring(c),
            "args_schema": {},  # Placeholder
        }
        _post_to_api(f"{api_url}/types/process", data)


@app.command()
def discover(
    project_dir: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            dir_okay=True,
            writable=False,
            readable=True,
            resolve_path=True,
            help="Path to the project directory to discover types from.",
        ),
    ],
    api_url: Annotated[
        _t.Optional[str],
        typer.Option(
            "--api-url",
            envvar="PLUGBOARD_API_URL",
            help=(
                "URL of the Plugboard API. "
                "Can also be set via PLUGBOARD_API_URL environment variable."
            ),
        ),
    ] = "http://localhost:8000",
) -> None:
    """Discover Plugboard types in a project and push them to the Plugboard API."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    if api_url is None:
        api_url = "http://localhost:8000"

    api_url = api_url.rstrip("/")

    with Progress(
        SpinnerColumn("arrow3"),
        TextColumn("[progress.description]{task.description}"),
    ) as progress:
        task = progress.add_task(f"Starting discovery in {project_dir}", total=None)

        # Check if project_dir is a package
        base_package = None
        if (project_dir / "__init__.py").exists():
            # It's a package, add parent to path
            sys.path.insert(0, str(project_dir.parent))
            base_package = project_dir.name
            logger.info(f"Detected package '{base_package}', adding parent directory to path")
        else:
            # Not a package, add dir directly
            sys.path.insert(0, str(project_dir))

        # Import plugboard
        try:
            import plugboard  # noqa: F401
            from plugboard.component import Component
            from plugboard.connector import Connector
            from plugboard.events import Event
            from plugboard.process import Process
        except ImportError:
            stderr.print("[red]Error: plugboard not found in target environment[/red]")
            raise typer.Exit(1)

        # Import everything in the project
        progress.update(task, description="Importing modules...")
        _import_recursive(project_dir, base_package)

        progress.update(task, description="Discovering components...")
        _discover_components(api_url, Component)

        progress.update(task, description="Discovering connectors...")
        _discover_connectors(api_url, Connector)

        progress.update(task, description="Discovering events...")
        _discover_events(api_url, Event)

        progress.update(task, description="Discovering processes...")
        _discover_processes(api_url, Process)

        progress.update(task, description="[green]Discovery complete[/green]")
