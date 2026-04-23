"""Smoke tests for examples/tutorials Python files."""

import os
from pathlib import Path
import subprocess
import sys
from typing import Iterator, Tuple

import pytest


SMOKE_TEST_TIMEOUT = 90
MAX_TRANSIENT_NETWORK_RETRIES = 1
PROJECT_ROOT = Path(__file__).parent.parent.parent
TRANSIENT_NETWORK_ERROR_SIGNATURES = (
    "ConnectError",
    "ReadTimeout",
    "RemoteProtocolError",
    "Server disconnected without sending a response",
)


@pytest.fixture(scope="module", autouse=True)
def ray_disable_uv_run() -> Iterator[None]:
    """Disable Ray's `uv run` runtime environment for smoke tests."""
    # uv run environment will prevent tests from running outside of the project root
    # This is necessary because the smoke tests run in a separate process
    os.environ["RAY_ENABLE_UV_RUN_RUNTIME_ENV"] = "0"
    yield
    os.environ.pop("RAY_ENABLE_UV_RUN_RUNTIME_ENV", None)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Dynamically generate test parameters for each tutorial file."""
    if "file_and_dir" in metafunc.fixturenames:
        # Get tutorial files
        tutorials_dir = PROJECT_ROOT / "examples" / "tutorials"

        if not tutorials_dir.exists():
            pytest.skip(f"Tutorials directory not found: {tutorials_dir}")

        tutorial_files = []
        for py_file in tutorials_dir.rglob("*.py"):
            working_dir = py_file.parent
            tutorial_files.append((py_file, working_dir))

        if not tutorial_files:
            pytest.skip("No Python files found in examples/tutorials")

        # Create test IDs for better test output
        test_ids = [str(py_file.relative_to(PROJECT_ROOT)) for py_file, _ in tutorial_files]

        metafunc.parametrize("file_and_dir", tutorial_files, ids=test_ids)


@pytest.mark.smoke
def test_tutorial_file_runs(file_and_dir: Tuple[Path, Path]) -> None:
    """Test that a tutorial file runs without errors."""
    py_file, working_dir = file_and_dir

    def _run_tutorial() -> tuple[subprocess.Popen[str], str, str]:
        process = subprocess.Popen(  # noqa: S603
            [sys.executable, py_file.name],
            cwd=working_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=SMOKE_TEST_TIMEOUT)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            pytest.skip(
                f"{py_file.relative_to(PROJECT_ROOT)} timed out after {SMOKE_TEST_TIMEOUT} seconds"
            )
        return process, stdout, stderr

    def _has_transient_network_error(*outputs: str) -> bool:
        return any(
            signature in output
            for output in outputs
            for signature in TRANSIENT_NETWORK_ERROR_SIGNATURES
        )

    try:
        process, stdout, stderr = _run_tutorial()
        retries = 0
        while (
            process.returncode != 0
            and retries < MAX_TRANSIENT_NETWORK_RETRIES
            and _has_transient_network_error(stdout, stderr)
        ):
            retries += 1
            process, stdout, stderr = _run_tutorial()

        if process.returncode != 0:
            if _has_transient_network_error(stdout, stderr):
                pytest.skip(
                    f"{py_file.relative_to(PROJECT_ROOT)} failed due to a transient external "
                    "network error"
                )
            error_msg = (
                f"Tutorial file {py_file.relative_to(PROJECT_ROOT)} "
                f"failed to run successfully.\n"
                f"Return code: {process.returncode}\n"
                f"STDOUT:\n{stdout}\n"
                f"STDERR:\n{stderr}"
            )
            pytest.fail(error_msg)
    except Exception as e:
        pytest.fail(f"Error running tutorial file {py_file.relative_to(PROJECT_ROOT)}: {e}")
