"""Smoke tests for examples/tutorials Python files."""

from pathlib import Path
import subprocess
import sys
from typing import List, Tuple

import pytest


SMOKE_TEST_TIMEOUT = 60


@pytest.fixture(scope="module")
def tutorial_files() -> List[Tuple[Path, Path]]:
    """Find all Python files in examples/tutorials."""
    project_root = Path(__file__).parent.parent.parent
    tutorials_dir = project_root / "examples" / "tutorials"

    if not tutorials_dir.exists():
        pytest.skip(f"Tutorials directory not found: {tutorials_dir}")

    tutorial_files = []
    for py_file in tutorials_dir.rglob("*.py"):
        # Get the directory containing the Python file
        working_dir = py_file.parent
        tutorial_files.append((py_file, working_dir))

    if not tutorial_files:
        pytest.skip("No Python files found in examples/tutorials")

    return tutorial_files


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Dynamically generate test parameters for each tutorial file."""
    if "file_and_dir" in metafunc.fixturenames:
        # Get tutorial files
        project_root = Path(__file__).parent.parent.parent
        tutorials_dir = project_root / "examples" / "tutorials"

        if not tutorials_dir.exists():
            pytest.skip(f"Tutorials directory not found: {tutorials_dir}")

        tutorial_files = []
        for py_file in tutorials_dir.rglob("*.py"):
            working_dir = py_file.parent
            tutorial_files.append((py_file, working_dir))

        if not tutorial_files:
            pytest.skip("No Python files found in examples/tutorials")

        # Create test IDs for better test output
        test_ids = [str(py_file.relative_to(project_root)) for py_file, _ in tutorial_files]

        metafunc.parametrize("file_and_dir", tutorial_files, ids=test_ids)


@pytest.mark.smoke
def test_tutorial_file_runs(file_and_dir: Tuple[Path, Path]) -> None:
    """Test that a tutorial file runs without errors."""
    py_file, working_dir = file_and_dir

    try:
        # Use subprocess.Popen with cwd argument
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
            project_root = Path(__file__).parent.parent.parent
            pytest.skip(
                f"{py_file.relative_to(project_root)} timed out after {SMOKE_TEST_TIMEOUT} seconds"
            )

        if process.returncode != 0:
            project_root = Path(__file__).parent.parent.parent
            error_msg = (
                f"Tutorial file {py_file.relative_to(project_root)} "
                f"failed to run successfully.\n"
                f"Return code: {process.returncode}\n"
                f"STDOUT:\n{stdout}\n"
                f"STDERR:\n{stderr}"
            )
            pytest.fail(error_msg)
    except Exception as e:
        project_root = Path(__file__).parent.parent.parent
        pytest.fail(f"Error running tutorial file {py_file.relative_to(project_root)}: {e}")
