"""Unit tests for the CLI."""

from typer.testing import CliRunner

from plugboard.cli import app


runner = CliRunner()


def test_cli_process_run() -> None:
    """Tests the process run command."""
    result = runner.invoke(app, ["process", "run", "tests/data/minimal-process.yaml"])
    assert result.exit_code == 0
