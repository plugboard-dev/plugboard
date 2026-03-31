"""Unit tests for the CLI.

Note: Tests which run async code synchronously from CLI entrypoints must be
marked async so that they do not interfere with pytest-asyncio's event loop.
"""

from pathlib import Path
import tempfile
import typing as _t
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import respx
from typer.testing import CliRunner

from plugboard.cli import app


runner = CliRunner()


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
        project_dir = Path(tmpdir) / "test_project"
        project_dir.mkdir()
        (project_dir / "__init__.py").write_text("")
        (project_dir / "test_file.py").write_text("")
        yield project_dir


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


def test_cli_server_discover(test_project_dir: Path) -> None:
    """Tests the server discover command."""
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
                str(test_project_dir),
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
