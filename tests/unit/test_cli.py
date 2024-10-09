"""Unit tests for the CLI."""

from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from plugboard.cli import app


runner = CliRunner()


def test_cli_process_run() -> None:
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
        mock_process.init.assert_called_once()
        # Process must be run
        mock_process.run.assert_called_once()
