"""Tool definitions for the Plugboard Go Copilot agent."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from copilot import define_tool
import msgspec
from pydantic import BaseModel, Field

from plugboard.diagram.mermaid import MermaidDiagram
from plugboard.process import Process, ProcessBuilder
from plugboard.schemas import ConfigSpec
from plugboard.utils import add_sys_path


class RunModelParams(BaseModel):
    """Parameters for running a Plugboard model from a YAML config file."""

    yaml_path: str = Field(
        description="Path to the YAML config file for the Plugboard model.",
    )


class MermaidDiagramParams(BaseModel):
    """Parameters for generating a Mermaid diagram URL from a YAML file."""

    yaml_path: str = Field(
        description="Path to the YAML config file for the Plugboard model.",
    )


def _read_yaml(path: Path) -> ConfigSpec:
    """Read and validate a YAML configuration file."""
    with open(path, "rb") as f:
        data = msgspec.yaml.decode(f.read())
    return ConfigSpec.model_validate(data)


def _build_process(config: ConfigSpec) -> Process:
    """Build a process from a config spec."""
    return ProcessBuilder.build(config.plugboard.process)


def create_run_model_tool() -> object:
    """Create the run_model tool for Copilot."""

    @define_tool(
        name="run_plugboard_model",
        description=(
            "Run a Plugboard model from a YAML configuration file. "
            "Returns the result of the model run, including any output or errors."
        ),
    )
    async def run_plugboard_model(params: RunModelParams) -> str:
        yaml_path = Path(params.yaml_path).resolve()
        if not yaml_path.exists():
            return f"Error: YAML file not found at {yaml_path}"
        if yaml_path.suffix not in (".yaml", ".yml"):
            return f"Error: File must be a .yaml or .yml file, got {yaml_path.suffix}"

        try:
            config = _read_yaml(yaml_path)
            with add_sys_path(yaml_path.parent):
                process = _build_process(config)

            async with process:
                await process.run()

            return f"Model ran successfully from {yaml_path}"
        except Exception as e:
            return f"Error running model: {type(e).__name__}: {e}"

    return run_plugboard_model


def create_mermaid_diagram_tool(
    on_url_generated: Callable[[str], None] | None = None,
) -> object:
    """Create the mermaid_diagram tool for Copilot.

    Args:
        on_url_generated: Optional callback invoked with the generated URL.
    """

    @define_tool(
        name="get_mermaid_diagram_url",
        description=(
            "Generate a Mermaid diagram URL for a Plugboard model "
            "defined in a YAML configuration file. Returns a URL to "
            "the Mermaid Live Editor where it can be viewed and edited."
        ),
    )
    async def get_mermaid_diagram_url(params: MermaidDiagramParams) -> str:
        yaml_path = Path(params.yaml_path).resolve()
        if not yaml_path.exists():
            return f"Error: YAML file not found at {yaml_path}"

        try:
            config = _read_yaml(yaml_path)
            with add_sys_path(yaml_path.parent):
                process = _build_process(config)

            diagram = MermaidDiagram.from_process(process)
            url = diagram.url

            if on_url_generated is not None:
                on_url_generated(url)

            return f"Mermaid diagram URL: {url}"
        except Exception as e:
            return f"Error generating diagram: {type(e).__name__}: {e}"

    return get_mermaid_diagram_url
