"""Unit tests for the CLI.

Note: Tests which run async code synchronously from CLI entrypoints must be
marked async so that they do not interfere with pytest-asyncio's event loop.
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from plugboard.cli import app


runner = CliRunner()


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


def test_cli_server_discover() -> None:
    """Tests the server discover command."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a minimal Python package
        project_dir = Path(tmpdir) / "test_project"
        project_dir.mkdir()
        (project_dir / "__init__.py").write_text("")
        
        # Mock the discovery functions
        with patch("plugboard.cli.server._import_recursive") as mock_import:
            with patch("plugboard.cli.server._discover_components") as mock_discover_components:
                with patch("plugboard.cli.server._discover_connectors") as mock_discover_connectors:
                    with patch("plugboard.cli.server._discover_events") as mock_discover_events:
                        with patch("plugboard.cli.server._discover_processes") as mock_discover_processes:
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
                            # Import must be called
                            mock_import.assert_called_once()
                            # All discovery functions must be called
                            mock_discover_components.assert_called_once()
                            mock_discover_connectors.assert_called_once()
                            mock_discover_events.assert_called_once()
                            mock_discover_processes.assert_called_once()


def test_cli_server_discover_with_env_var() -> None:
    """Tests the server discover command with environment variable."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a minimal Python package
        project_dir = Path(tmpdir) / "test_project"
        project_dir.mkdir()
        (project_dir / "__init__.py").write_text("")
        
        # Mock the discovery functions
        with patch("plugboard.cli.server._import_recursive"):
            with patch("plugboard.cli.server._discover_components"):
                with patch("plugboard.cli.server._discover_connectors"):
                    with patch("plugboard.cli.server._discover_events"):
                        with patch("plugboard.cli.server._discover_processes"):
                            result = runner.invoke(
                                app,
                                ["server", "discover", str(project_dir)],
                                env={"PLUGBOARD_API_URL": "http://env-test:9000"},
                            )
                            # CLI must run without error
                            assert result.exit_code == 0
                            assert "Discovery complete" in result.stdout
