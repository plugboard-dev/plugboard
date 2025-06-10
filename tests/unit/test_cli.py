"""Unit tests for the CLI.

Note: Tests which run async code synchronously from CLI entrypoints must be
marked async so that they do not interfere with pytest-asyncio's event loop.
"""

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
