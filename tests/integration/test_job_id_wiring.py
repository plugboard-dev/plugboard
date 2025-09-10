"""Tests mechanisms for setting and getting job IDs throughout the application.

Note: Tests which run async code synchronously from CLI entrypoints must be
marked async so that they do not interfere with pytest-asyncio's event loop.
"""

from __future__ import annotations

import os
from pathlib import Path
import typing as _t
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from plugboard.cli import app
from plugboard.component import Component
from plugboard.component.io_controller import IOController as IO
from plugboard.process import LocalProcess, Process, ProcessBuilder, RayProcess
from plugboard.schemas import ProcessSpec
from plugboard.state import DictStateBackend, SqliteStateBackend
from plugboard.utils import DI
from plugboard.utils.entities import EntityIdGen


runner = CliRunner()


class MockComponent(Component):
    """A mock component for testing."""

    io = IO(inputs=["test_input"], outputs=["test_output"])
    exports = ["job_id_during_init"]

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


class ProcessBuilderMock:
    """A mock process builder for testing."""

    def __init__(self) -> None:
        """Initialize the mock process builder."""
        # Store the original build method. Must occur before patching.
        self._actual_build_fn = ProcessBuilder.build
        self._built_process: _t.Optional[Process] = None

    @property
    def built_process(self) -> _t.Optional[Process]:
        """Get the built process."""
        return self._built_process

    def build(self, spec: ProcessSpec) -> Process:
        """Build the process."""
        self._built_process = self._actual_build_fn(spec)
        setattr(self._built_process, "run", lambda: self._mock_process_run(self._built_process))
        return self._built_process

    @staticmethod
    async def _mock_process_run(process: Process) -> None:
        """Mock run method for the process."""
        setattr(process, "saved_job_id", process.state.job_id)


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
def yaml_job_id() -> str:
    """Return a job ID for testing."""
    return "Job_predefined12345678"


@pytest.fixture
def config_file_with_job_id(tmp_path: Path, yaml_job_id: str) -> Path:
    """Create a config file with a predefined job_id."""
    config_content = f"""
    plugboard:
      process:
        args:
          state:
            args:
              job_id: {yaml_job_id}
          components:
          - type: tests.integration.test_process_with_components_run.A
            args:
              name: "a"
              iters: 10
    """
    config_file = tmp_path / "process-with-job-id.yaml"
    config_file.write_text(config_content)
    return config_file


@pytest.mark.asyncio
async def test_cli_process_run_with_yaml_job_id(
    config_file_with_job_id: Path, yaml_job_id: str
) -> None:
    """Test running a process with a job ID specified in the YAML file."""
    process_builder = ProcessBuilderMock()
    job_id = yaml_job_id

    with patch("plugboard.cli.process.ProcessBuilder.build", side_effect=process_builder.build):
        result = runner.invoke(app, ["process", "run", str(config_file_with_job_id)])
        # CLI must run without error
        assert result.exit_code == 0

    # Verify the process was built and has the expected job ID
    assert process_builder.built_process is not None
    assert getattr(process_builder.built_process, "saved_job_id", job_id)


@pytest.mark.asyncio
async def test_cli_process_run_with_cmd_job_id(minimal_config_file: Path) -> None:
    """Test running a process with a job ID specified via the command line argument."""
    process_builder = ProcessBuilderMock()
    job_id = "Job_cmdline12345678"

    with patch("plugboard.cli.process.ProcessBuilder.build", side_effect=process_builder.build):
        result = runner.invoke(
            app, ["process", "run", "--job-id", job_id, str(minimal_config_file)]
        )
        # CLI must run without error
        assert result.exit_code == 0

    # Verify the process was built and has the expected job ID
    assert process_builder.built_process is not None
    assert getattr(process_builder.built_process, "saved_job_id", job_id)


@pytest.mark.asyncio
async def test_cli_process_run_override_yaml_job_id(config_file_with_job_id: Path) -> None:
    """Test overriding a YAML-specified job ID with a command line argument."""
    process_builder = ProcessBuilderMock()
    job_id = "Job_cmdline12345678"

    with patch("plugboard.cli.process.ProcessBuilder.build", side_effect=process_builder.build):
        result = runner.invoke(
            app, ["process", "run", "--job-id", job_id, str(config_file_with_job_id)]
        )
        # CLI must run without error
        assert result.exit_code == 0

    # Verify the process was built and has the expected job ID
    assert process_builder.built_process is not None
    assert getattr(process_builder.built_process, "saved_job_id", job_id)


@pytest.mark.asyncio
async def test_cli_process_run_with_env_var(minimal_config_file: Path) -> None:
    """Test running a process with a job ID specified via environment variable."""
    process_builder = ProcessBuilderMock()
    job_id: str = "Job_envvar12345678"

    with patch.dict(os.environ, {"PLUGBOARD_JOB_ID": job_id}):
        with patch("plugboard.cli.process.ProcessBuilder.build", side_effect=process_builder.build):
            result = runner.invoke(app, ["process", "run", str(minimal_config_file)])
            # CLI must run without error
            assert result.exit_code == 0

    # Verify the process was built and has the expected job ID
    assert process_builder.built_process is not None
    assert getattr(process_builder.built_process, "saved_job_id", job_id)


@pytest.mark.asyncio
async def test_cli_process_run_with_no_job_id(minimal_config_file: Path) -> None:
    """Test running a process with no job ID specified (auto-generated)."""
    process_builder = ProcessBuilderMock()

    with patch("plugboard.cli.process.ProcessBuilder.build", side_effect=process_builder.build):
        result = runner.invoke(app, ["process", "run", str(minimal_config_file)])
        # CLI must run without error
        assert result.exit_code == 0

    # Verify the process was built and has the expected job ID
    assert process_builder.built_process is not None
    assert EntityIdGen.is_job_id(getattr(process_builder.built_process, "saved_job_id"))


@pytest.mark.asyncio
async def test_direct_process_with_job_id() -> None:
    """Test building a process directly with a specified job ID."""
    # Create a state backend with a specific job ID
    state: DictStateBackend = DictStateBackend(job_id="Job_direct12345678")

    component: MockComponent = MockComponent()
    process: LocalProcess = LocalProcess(components=[component], connectors=[], state=state)

    async with process:
        # The specified job ID should be set in the process and component
        assert process.state.job_id == "Job_direct12345678"
        assert component.job_id_during_init == "Job_direct12345678"


@pytest.mark.asyncio
async def test_direct_process_with_env_var() -> None:
    """Test building a process without a job ID while environment variable is set."""
    # Set the environment variable to match the job ID to avoid conflict
    job_id: str = "Job_direct12345678"

    with patch.dict(os.environ, {"PLUGBOARD_JOB_ID": job_id}):
        # Create a state backend without a job ID
        state: DictStateBackend = DictStateBackend()

        component: MockComponent = MockComponent()
        process: LocalProcess = LocalProcess(components=[component], connectors=[], state=state)

        async with process:
            # The specified job ID should be set in the process and component
            assert process.state.job_id == job_id
            assert component.job_id_during_init == job_id


@pytest.mark.asyncio
async def test_direct_process_with_job_id_and_env_var() -> None:
    """Test building a process with a job ID while environment variable is set with same value."""
    # Set the environment variable to match the job ID to avoid conflict
    job_id: str = "Job_direct12345678"

    with patch.dict(os.environ, {"PLUGBOARD_JOB_ID": job_id}):
        # Create a state backend with a specific job ID
        state: DictStateBackend = DictStateBackend(job_id=job_id)

        component: MockComponent = MockComponent()
        process: LocalProcess = LocalProcess(components=[component], connectors=[], state=state)

        async with process:
            # The specified job ID should be set in the process and component
            assert process.state.job_id == job_id
            assert component.job_id_during_init == job_id


@pytest.mark.asyncio
async def test_direct_process_with_conflicting_job_ids() -> None:
    """Test building a process with a job ID that conflicts with the environment variable."""
    with patch.dict(os.environ, {"PLUGBOARD_JOB_ID": "Job_envconf12345678"}):
        # Create a state backend with a different job ID
        state: DictStateBackend = DictStateBackend(job_id="Job_dircon12345678")
        with pytest.raises(RuntimeError, match="Job ID .* does not match environment variable"):
            # This should raise a RuntimeError because the job IDs don't match
            async with state:
                pass


@pytest.mark.asyncio
async def test_direct_process_without_job_id() -> None:
    """Test building a process without specifying a job ID."""
    # Create a state backend without a job ID
    state: DictStateBackend = DictStateBackend()

    component: MockComponent = MockComponent()
    process: LocalProcess = LocalProcess(components=[component], connectors=[], state=state)

    async with process:
        # A job ID should have been auto-generated
        assert process.state.job_id is not None
        assert EntityIdGen.is_job_id(process.state.job_id)

        # The job ID should be available in the DI container during component init
        assert component.job_id_during_init == process.state.job_id


@pytest.mark.asyncio
async def test_direct_process_without_job_id_multiple_runs() -> None:
    """Test building a process without specifying a job ID multiple times."""
    # Create a state backend without a job ID
    state: DictStateBackend = DictStateBackend()

    component: MockComponent = MockComponent()
    process: LocalProcess = LocalProcess(components=[component], connectors=[], state=state)

    job_id_history = set([])
    num_runs = 3
    for _ in range(num_runs):
        async with process:
            # A job ID should have been auto-generated
            assert process.state.job_id is not None
            assert EntityIdGen.is_job_id(process.state.job_id)

            # The job ID should be available in the DI container during component init
            assert component.job_id_during_init == process.state.job_id

            # Store the job ID to check for uniqueness
            job_id_history.add(process.state.job_id)

    # Ensure all job IDs are unique
    assert len(job_id_history) == num_runs


@pytest.mark.asyncio
async def test_direct_process_without_job_id_multiple_runs_multiprocessing() -> None:
    """Test building a process without a job ID in a multiprocessing context."""
    # Create a state backend without a specific job ID
    state: SqliteStateBackend = SqliteStateBackend()

    components: list[MockComponent] = [MockComponent(name=f"mock-component-{i}") for i in range(3)]
    process: RayProcess = RayProcess(components=components, connectors=[], state=state)

    job_id_history: set[str] = set([])
    num_runs: int = 3
    for _ in range(num_runs):
        async with process:
            # A job ID should have been auto-generated
            assert process.state.job_id is not None
            assert EntityIdGen.is_job_id(process.state.job_id)

            # Ensure the job ID is set correctly in each component
            for component in components:
                assert component.job_id_during_init == process.state.job_id

            # Store the job ID to check for uniqueness
            job_id_history.add(process.state.job_id)

    # Ensure all job IDs are unique
    assert len(job_id_history) == num_runs
