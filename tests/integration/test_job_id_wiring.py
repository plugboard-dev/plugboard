"""Tests mechanisms for setting and getting job IDs throughout the application."""

import os
from pathlib import Path
import typing as _t
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from plugboard.cli.process import _read_yaml
from plugboard.component import Component
from plugboard.component.io_controller import IOController as IO
from plugboard.process import ProcessBuilder
from plugboard.process.local_process import LocalProcess
from plugboard.state import DictStateBackend
from plugboard.utils import DI
from plugboard.utils.entities import EntityIdGen


runner = CliRunner()


class MockComponent(Component):
    """A mock component for testing."""

    # Define custom IO for this component to satisfy the abstract base class requirement
    io = IO(inputs=["test_input"], outputs=["test_output"])

    def __init__(self, *args: _t.Any, name: str = "mock_component", **kwargs: _t.Any) -> None:
        """Initialize the mock component."""
        super().__init__(*args, name=name, **kwargs)
        self.job_id_during_init: _t.Optional[str] = None

    async def init(self) -> None:
        """Initialize the component."""
        # Access job_id from DI to verify it's correctly set
        self.job_id_during_init = DI.job_id.resolve_sync()

    async def step(self) -> None:
        """Step the component."""
        pass


@pytest.fixture
def minimal_config_file(tmp_path: Path) -> Path:
    """Create a minimal config file without a job_id."""
    config_content = """
    plugboard:
      process:
        args:
          components:
          - type: tests.integration.test_process_with_components_run.A
            args:
              name: "a"
              iters: 10
    """
    config_file = tmp_path / "minimal-process.yaml"
    config_file.write_text(config_content)
    return config_file


@pytest.fixture
def config_file_with_job_id(tmp_path: Path) -> Path:
    """Create a config file with a predefined job_id."""
    config_content = """
    plugboard:
      process:
        args:
          state:
            args:
              job_id: "Job_predefined12345678"
          components:
          - type: tests.integration.test_process_with_components_run.A
            args:
              name: "a"
              iters: 10
    """
    config_file = tmp_path / "process-with-job-id.yaml"
    config_file.write_text(config_content)
    return config_file


def test_cli_process_run_with_yaml_job_id(config_file_with_job_id: Path) -> None:
    """Test running a process with a job ID specified in the YAML file."""
    # Read the config directly without running the whole CLI
    config_spec = _read_yaml(config_file_with_job_id)

    # Verify that the job ID in the YAML was loaded correctly
    assert config_spec.plugboard.process.args.state.args.job_id == "Job_predefined12345678"

    # Test that the process builder would receive this job ID
    process = ProcessBuilder.build(config_spec.plugboard.process)
    assert process.state.job_id == "Job_predefined12345678"


def test_cli_process_run_with_cmd_job_id(minimal_config_file: Path) -> None:
    """Test running a process with a job ID specified via the command line argument."""
    # Read the config directly without running the whole CLI
    config_spec = _read_yaml(minimal_config_file)

    # Set the job ID as if it came from the command line
    config_spec.plugboard.process.args.state.args.job_id = "Job_cmdline12345678"

    # Verify the job ID was set correctly
    assert config_spec.plugboard.process.args.state.args.job_id == "Job_cmdline12345678"

    # Test that the process builder would receive this job ID
    process = ProcessBuilder.build(config_spec.plugboard.process)
    assert process.state.job_id == "Job_cmdline12345678"


def test_cli_process_run_override_yaml_job_id(config_file_with_job_id: Path) -> None:
    """Test overriding a YAML-specified job ID with a command line argument."""
    # Read the config directly without running the whole CLI
    config_spec = _read_yaml(config_file_with_job_id)

    # Verify the original job ID from YAML
    assert config_spec.plugboard.process.args.state.args.job_id == "Job_predefined12345678"

    # Override the job ID as if it came from the command line
    config_spec.plugboard.process.args.state.args.job_id = "Job_override12345678"

    # Verify the job ID was overridden correctly
    assert config_spec.plugboard.process.args.state.args.job_id == "Job_override12345678"

    # Test that the process builder would receive this job ID
    process = ProcessBuilder.build(config_spec.plugboard.process)
    assert process.state.job_id == "Job_override12345678"


@pytest.mark.asyncio
async def test_cli_process_run_with_env_var(minimal_config_file: Path) -> None:
    """Test running a process with a job ID specified via environment variable."""
    # Define the job ID we want to set in the environment
    job_id_env: str = "Job_envvar12345678"

    # Set the environment variable
    with patch.dict(os.environ, {"PLUGBOARD_JOB_ID": job_id_env}):
        # Read the config directly without running the whole CLI
        config_spec = _read_yaml(minimal_config_file)

        # Verify no job ID was set in the config
        assert config_spec.plugboard.process.args.state.args.job_id is None

        # Create a process - it should pick up the job ID from the environment
        process = ProcessBuilder.build(config_spec.plugboard.process)

        # Initialize to ensure job_id is set from env
        async with process:
            # The job ID from the environment should be used
            assert process.state.job_id == job_id_env


@pytest.mark.asyncio
async def test_cli_process_run_with_no_job_id(minimal_config_file: Path) -> None:
    """Test running a process with no job ID specified (auto-generated)."""
    with patch.dict(os.environ, {}, clear=True):  # Clear environment variables
        # Read the config directly without running the whole CLI
        config_spec = _read_yaml(minimal_config_file)

        # Verify no job ID was set in the config
        assert config_spec.plugboard.process.args.state.args.job_id is None

        # Create a process - it should generate a job ID
        process = ProcessBuilder.build(config_spec.plugboard.process)

        # Initialize to ensure job_id is generated
        async with process:
            # A job ID should have been auto-generated
            assert process.state.job_id is not None
            assert EntityIdGen.is_job_id(process.state.job_id)


@pytest.mark.asyncio
async def test_direct_process_with_job_id() -> None:
    """Test building a process directly with a specified job ID."""
    # Create a state backend with a specific job ID
    state: DictStateBackend = DictStateBackend(job_id="Job_direct12345678")

    # Create a mock component that will check the job ID
    component: MockComponent = MockComponent()

    # Create a process with the state backend
    process: LocalProcess = LocalProcess(components=[component], connectors=[], state=state)

    # We need to set up a container context for the job_id
    async with process:
        # The job ID should be available in the process
        assert process.state.job_id == "Job_direct12345678"

        # The job ID should be available in the DI container during component init
        assert component.job_id_during_init == "Job_direct12345678"


@pytest.mark.asyncio
async def test_direct_process_with_job_id_and_env_var() -> None:
    """Test building a process with a job ID while environment variable is set."""
    # Set the environment variable to match the job ID to avoid conflict
    job_id: str = "Job_direct12345678"

    with patch.dict(os.environ, {"PLUGBOARD_JOB_ID": job_id}):
        # Create a state backend with a specific job ID
        state: DictStateBackend = DictStateBackend(job_id=job_id)

        # Create a mock component
        component: MockComponent = MockComponent()

        # Create a process with the state backend
        process: LocalProcess = LocalProcess(components=[component], connectors=[], state=state)

        # Initialize and run the process
        async with process:
            # The job ID from the direct argument should take precedence
            assert process.state.job_id == job_id
            assert component.job_id_during_init == job_id


@pytest.mark.asyncio
async def test_direct_process_without_job_id() -> None:
    """Test building a process without specifying a job ID."""
    # Create a state backend without a job ID
    state: DictStateBackend = DictStateBackend()

    # Create a mock component
    component: MockComponent = MockComponent()

    # Create a process with the state backend
    process: LocalProcess = LocalProcess(components=[component], connectors=[], state=state)

    # Initialize and run the process - we'll let the DI container create a job ID
    async with process:
        # A job ID should have been auto-generated
        assert process.state.job_id is not None
        assert EntityIdGen.is_job_id(process.state.job_id)

        # The job ID should be available in the DI container during component init
        assert component.job_id_during_init == process.state.job_id


@pytest.mark.asyncio
async def test_direct_process_with_conflicting_job_ids() -> None:
    """Test building a process with a job ID that conflicts with the environment variable."""
    # Set the environment variable
    with patch.dict(os.environ, {"PLUGBOARD_JOB_ID": "Job_envconf12345678"}):
        # Create a state backend with a different job ID
        state: DictStateBackend = DictStateBackend(job_id="Job_dircon12345678")
        with pytest.raises(RuntimeError, match="Job ID .* does not match environment variable"):
            # This should raise a RuntimeError because the job IDs don't match
            async with state:
                pass  # This code should not execute
