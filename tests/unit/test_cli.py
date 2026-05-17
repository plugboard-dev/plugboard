"""Unit tests for the CLI.

Note: Tests which run async code synchronously from CLI entrypoints must be
marked async so that they do not interfere with pytest-asyncio's event loop.
"""

import json
from pathlib import Path
import tempfile
import textwrap
import typing as _t
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import respx
from typer.testing import CliRunner

from plugboard.cli import app
from plugboard.cli.ai import _AGENTS_MD


runner = CliRunner()


def _create_test_project(
    base_path: Path,
    *,
    as_package: bool = True,
    include_hidden_dir: bool = False,
) -> Path:
    """Create a minimal Python project for CLI discovery tests."""
    project_dir = base_path / "test_project"
    project_dir.mkdir()

    if as_package:
        (project_dir / "__init__.py").write_text("")
        (project_dir / "test_file.py").write_text("")
    else:
        (project_dir / "test_file.py").write_text(
            textwrap.dedent("""
            from plugboard.component import Component, IOController as IO


            class VisibleComponent(Component):
                io = IO(outputs=["out"])

                async def step(self) -> None:
                    self.out = 1
            """).strip()
        )

    if include_hidden_dir:
        hidden_dir = project_dir / ".venv"
        hidden_dir.mkdir()
        (hidden_dir / "bad_module.py").write_text('raise RuntimeError("should not import")')

    return project_dir


def test_cli_version() -> None:
    """Tests the version command."""
    result = runner.invoke(app, ["version"])
    # CLI must run without error
    assert result.exit_code == 0
    # Must output version information
    assert "Plugboard version:" in result.stdout
    assert "Platform:" in result.stdout
    assert "Python version:" in result.stdout


@pytest.fixture
def test_project_dir() -> _t.Iterator[Path]:
    """Create a minimal Python package for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield _create_test_project(Path(tmpdir))


@pytest.mark.asyncio
async def test_cli_process_run() -> None:
    """Tests the process run command."""
    with patch("plugboard.cli.process.ProcessBuilder") as mock_process_builder:
        mock_process = AsyncMock()
        mock_process_builder.build.return_value = mock_process
        result = runner.invoke(app, ["process", "run", "tests/data/minimal-process.yaml"])
        # CLI must run without error
        assert result.exit_code == 0
        assert "Process complete" in result.stdout
        # Process must be built
        mock_process_builder.build.assert_called_once()
        # Process must be initialised
        mock_process.__aenter__.assert_called_once()
        # Process must be run
        mock_process.run.assert_called_once()
        # Process must be destroyed
        mock_process.__aexit__.assert_called_once()


def test_cli_process_tune() -> None:
    """Tests the process tune command."""
    with patch("plugboard.cli.process.Tuner") as mock_tuner_cls:
        mock_tuner = MagicMock()
        mock_tuner_cls.return_value = mock_tuner
        result = runner.invoke(
            app, ["process", "tune", "tests/data/minimal-process-with-tune.yaml"]
        )
        # CLI must run without error
        assert result.exit_code == 0
        assert "Tune job complete" in result.stdout
        # Tuner must be instantiated
        mock_tuner_cls.assert_called_once()
        # Tuner must be run
        mock_tuner.run.assert_called_once()


def test_cli_process_diagram() -> None:
    """Tests the process diagram command."""
    result = runner.invoke(app, ["process", "diagram", "tests/data/minimal-process.yaml"])
    # CLI must run without error
    assert result.exit_code == 0
    # Must output a Mermaid flowchart
    assert "flowchart" in result.stdout


@pytest.mark.asyncio
async def test_cli_process_run_with_local_override() -> None:
    """Tests the process run command with --process-type local."""
    with patch("plugboard.cli.process.ProcessBuilder") as mock_process_builder:
        mock_process = AsyncMock()
        mock_process_builder.build.return_value = mock_process
        result = runner.invoke(
            app,
            ["process", "run", "tests/data/minimal-process.yaml", "--process-type", "local"],
        )
        # CLI must run without error
        assert result.exit_code == 0
        assert "Process complete" in result.stdout
        # Process must be built with LocalProcess type
        mock_process_builder.build.assert_called_once()
        call_args = mock_process_builder.build.call_args
        process_spec = call_args[0][0]
        assert process_spec.type == "plugboard.process.LocalProcess"
        assert process_spec.connector_builder.type == "plugboard.connector.AsyncioConnector"


@pytest.mark.asyncio
async def test_cli_process_run_with_ray_override() -> None:
    """Tests the process run command with --process-type ray."""
    with patch("plugboard.cli.process.ProcessBuilder") as mock_process_builder:
        mock_process = AsyncMock()
        mock_process_builder.build.return_value = mock_process
        result = runner.invoke(
            app,
            ["process", "run", "tests/data/minimal-process.yaml", "--process-type", "ray"],
        )
        # CLI must run without error
        assert result.exit_code == 0
        assert "Process complete" in result.stdout
        # Process must be built with RayProcess type
        mock_process_builder.build.assert_called_once()
        call_args = mock_process_builder.build.call_args
        process_spec = call_args[0][0]
        assert process_spec.type == "plugboard.process.RayProcess"
        assert process_spec.connector_builder.type == "plugboard.connector.RayConnector"
        assert process_spec.args.state.type == "plugboard.state.RayStateBackend"


def test_cli_process_validate() -> None:
    """Tests the process validate command."""
    result = runner.invoke(app, ["process", "validate", "tests/data/minimal-process.yaml"])
    # CLI must run without error for a valid config
    assert result.exit_code == 0
    assert "Validation passed" in result.stdout


def test_cli_process_validate_invalid() -> None:
    """Tests the process validate command with an invalid process."""
    with patch("plugboard.cli.process.validate_process") as mock_validate:
        mock_validate.return_value = ["Component 'x' has unconnected inputs: ['in_1']"]
        result = runner.invoke(app, ["process", "validate", "tests/data/minimal-process.yaml"])
        assert result.exit_code == 1
        assert "Validation failed" in result.stderr


def test_cli_ai_init(tmp_path: Path) -> None:
    """Tests the ai init command creates AGENTS.md."""
    result = runner.invoke(app, ["ai", "init", str(tmp_path)])
    assert result.exit_code == 0
    assert "Created" in result.stdout
    # File must exist with expected content
    agents_md = tmp_path / "AGENTS.md"
    assert agents_md.exists()
    content = agents_md.read_text()
    assert "Plugboard" in content


def test_cli_ai_init_already_exists(tmp_path: Path) -> None:
    """Tests the ai init command fails when AGENTS.md already exists."""
    (tmp_path / "AGENTS.md").write_text("existing content")
    result = runner.invoke(app, ["ai", "init", str(tmp_path)])
    assert result.exit_code == 1
    # Error is printed to stderr which typer captures in output
    assert "already exists" in result.output


def test_cli_ai_init_default_directory() -> None:
    """Tests the ai init command uses current directory by default."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = Path.cwd()
        try:
            import os

            os.chdir(tmpdir)
            result = runner.invoke(app, ["ai", "init"])
            assert result.exit_code == 0
            assert (Path(tmpdir) / "AGENTS.md").exists()
        finally:
            os.chdir(original_cwd)


def test_cli_ai_agents_template_is_packaged_file() -> None:
    """Tests the AI template is a real package file rather than a symlink."""
    assert _AGENTS_MD.exists()
    assert _AGENTS_MD.is_file()
    assert not _AGENTS_MD.is_symlink()


@pytest.mark.parametrize(
    ("as_package", "include_hidden_dir", "expected_component_name"),
    [
        (True, False, None),
        (False, True, "VisibleComponent"),
    ],
)
def test_cli_server_discover(
    tmp_path: Path,
    as_package: bool,
    include_hidden_dir: bool,
    expected_component_name: str | None,
) -> None:
    """Tests the server discover command."""
    project_dir = _create_test_project(
        tmp_path,
        as_package=as_package,
        include_hidden_dir=include_hidden_dir,
    )

    with respx.mock:
        # Mock all the API endpoints
        component_route = respx.post("http://test:8000/types/component").respond(
            json={"status": "ok"}
        )
        connector_route = respx.post("http://test:8000/types/connector").respond(
            json={"status": "ok"}
        )
        event_route = respx.post("http://test:8000/types/event").respond(json={"status": "ok"})
        process_route = respx.post("http://test:8000/types/process").respond(json={"status": "ok"})

        result = runner.invoke(
            app,
            [
                "server",
                "discover",
                str(project_dir),
                "--api-url",
                "http://test:8000",
            ],
        )

        # CLI must run without error
        assert result.exit_code == 0
        assert "Discovery complete" in result.stdout

        # At minimum, should have discovered plugboard's built-in types
        # The exact number may vary, but we expect some calls to each endpoint
        assert component_route.called
        assert connector_route.called
        assert event_route.called
        assert process_route.called
        if expected_component_name is not None:
            assert result.exception is None
            assert any(
                json.loads(call.request.content)["name"] == expected_component_name
                for call in component_route.calls
            )


def test_cli_server_discover_with_env_var(test_project_dir: Path) -> None:
    """Tests the server discover command with environment variable."""
    with respx.mock:
        # Mock all the API endpoints with the env var URL
        respx.post("http://env-test:9000/types/component").respond(json={"status": "ok"})
        respx.post("http://env-test:9000/types/connector").respond(json={"status": "ok"})
        respx.post("http://env-test:9000/types/event").respond(json={"status": "ok"})
        respx.post("http://env-test:9000/types/process").respond(json={"status": "ok"})

        result = runner.invoke(
            app,
            ["server", "discover", str(test_project_dir)],
            env={"PLUGBOARD_API_URL": "http://env-test:9000"},
        )

        # CLI must run without error
        assert result.exit_code == 0
        assert "Discovery complete" in result.stdout
