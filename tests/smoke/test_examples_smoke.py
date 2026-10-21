"""Execute offline example entrypoints and check their results in isolated directories."""

import ast
import csv
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest


SMOKE_TEST_TIMEOUT = 90
PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = PROJECT_ROOT / "examples"
TUTORIALS = EXAMPLES / "tutorials"
# Helper modules are deliberately excluded. Network and Tune examples have focused
# regression tests; Ray scripts are exercised separately below.
LOCAL_ENTRYPOINTS = [
    "001_hello_world/hello_world.py",
    "001_hello_world/model.yaml",
    "002_complex_processes/branching.py",
    "002_complex_processes/branching.yaml",
    "002_complex_processes/parameters.py",
    "002_complex_processes/parameters.yaml",
    "002_complex_processes/loop.py",
    "002_complex_processes/loop.yaml",
    "005_events/hello_events.py",
    "005_events/model.yaml",
]


def run_example(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run an entrypoint; unexpected hangs and nonzero exits fail with captured output."""
    env = {
        **os.environ,
        "RAY_ENABLE_UV_RUN_RUNTIME_ENV": "0",
        "PLUGBOARD_IO_READ_TIMEOUT": "0.1",
    }
    try:
        result = subprocess.run(  # noqa: S603
            [sys.executable, *args],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=SMOKE_TEST_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(
            f"{args} timed out after {SMOKE_TEST_TIMEOUT}s\n"
            f"STDOUT: {exc.stdout}\nSTDERR: {exc.stderr}"
        )
    assert result.returncode == 0, f"{args}\n{result.stdout}\n{result.stderr}"
    return result


def numbers(path: Path) -> list[float]:
    """Read an example's numeric text output."""
    return [float(line) for line in path.read_text().splitlines()]


@pytest.mark.smoke
@pytest.mark.parametrize("entrypoint", LOCAL_ENTRYPOINTS)
def test_local_entrypoint(entrypoint: str, tmp_path: Path) -> None:
    """Exercise Python and YAML entrypoints and assert computed output."""
    source = TUTORIALS / entrypoint
    shutil.copytree(source.parent, tmp_path, dirs_exist_ok=True)
    args = (
        [source.name]
        if source.suffix == ".py"
        else ["-m", "plugboard", "process", "run", source.name]
    )
    run_example(args, tmp_path)
    if source.parent.name == "001_hello_world":
        count = 5 if source.suffix == ".py" else 10
        assert numbers(tmp_path / "b.txt") == list(range(0, count * 2, 2))
    elif source.stem in {"branching", "parameters"}:
        inputs = numbers(tmp_path / "input.txt")
        outputs = numbers(tmp_path / "output.txt")
        assert len(inputs) == len(outputs) == 5
        expected = [3 * x + 10 if source.stem == "branching" else 2.5 * x for x in inputs]
        assert outputs == pytest.approx(expected)
    elif source.stem == "loop":
        outputs = numbers(tmp_path / "cumulative-sum.txt")
        assert len(outputs) == 5
        previous = 0.0
        for value in outputs:
            assert 0 <= value - previous <= 10
            previous = value * (0.5 if source.suffix == ".py" else 2)
    else:
        for name, lower, upper in [("high.csv", 0.8, 1), ("low.csv", 0, 0.2)]:
            with (tmp_path / name).open() as stream:
                rows = list(csv.DictReader(stream))
            assert rows
            assert all(lower <= float(row["value"]) <= upper for row in rows)


@pytest.mark.smoke
@pytest.mark.parametrize("notebook", sorted(EXAMPLES.rglob("*.ipynb")), ids=lambda p: p.stem)
def test_notebook_sources_and_links(notebook: Path) -> None:
    """Compile every notebook and validate Colab targets against the repository tree."""
    cells = json.loads(notebook.read_text())["cells"]
    links = []
    for index, cell in enumerate(cells):
        source = "".join(cell["source"])
        links.extend(re.findall(r"https://colab.research.google.com/github/[^)\s]+", source))
        if cell["cell_type"] == "code":
            # IPython handles shell commands, magics, and top-level await.
            from IPython.core.interactiveshell import InteractiveShell

            transformed = InteractiveShell.instance().transform_cell(source)
            compile(transformed, f"{notebook}:{index}", "exec", ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
    assert links, f"No Colab badge in {notebook}"
    expected = (
        "https://colab.research.google.com/github/plugboard-dev/plugboard/blob/main/"
        + notebook.relative_to(PROJECT_ROOT).as_posix()
    )
    assert links == [expected]


@pytest.mark.smoke
def test_simple_model_notebook(tmp_path: Path) -> None:
    """Execute the offline notebook's code cells, including its process, and check totals."""
    source = EXAMPLES / "demos/fundamentals/001_simple_model/simple-model.ipynb"
    shutil.copytree(source.parent, tmp_path, dirs_exist_ok=True)
    # Keep notebook cell order and top-level await. Only environment installation
    # and the final shell display are omitted; dependencies are already installed.
    run_example(
        [
            "-c",
            """
import ast
import asyncio
import json
from pathlib import Path

async def main():
    namespace = {}
    for cell in json.loads(Path('simple-model.ipynb').read_text())['cells']:
        source = ''.join(cell['source'])
        if cell['cell_type'] == 'code' and not any(
            line.startswith('!') for line in source.splitlines()
        ):
            # Execute in shared notebook globals, preserving state between cells.
            code = compile(source, '<notebook>', 'exec', flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
            result = eval(code, namespace)
            if result is not None:
                await result

asyncio.run(main())
""",
        ],
        tmp_path,
    )
    with (tmp_path / "output.csv").open() as stream:
        values = [float(row["value_to_save"]) for row in csv.DictReader(stream)]
    assert values == [sum(range(1, i + 1)) for i in range(1, 11)]


@pytest.mark.smoke
@pytest.mark.parametrize("config", sorted(TUTORIALS.rglob("*.yaml")), ids=lambda p: p.name)
def test_tutorial_yaml_schema(config: Path) -> None:
    """Validate all tutorial configurations, including resource and tuning examples."""
    from plugboard.cli.process import _read_yaml

    parsed = _read_yaml(config)
    assert parsed.plugboard.process.args.components
    assert parsed.plugboard.process.args.connectors


def test_timeout_is_a_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Prevent hangs from silently becoming successful skips again."""

    def hang(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="example", timeout=SMOKE_TEST_TIMEOUT)

    monkeypatch.setattr(subprocess, "run", hang)
    with pytest.raises(pytest.fail.Exception, match="timed out"):
        run_example(["example.py"], tmp_path)


@pytest.mark.smoke
@pytest.mark.parametrize("entrypoint", ["hello_ray.py", "resources_example.py"])
def test_ray_entrypoint(entrypoint: str, tmp_path: Path) -> None:
    """Run Ray tutorial scripts, including their local Ray resource declarations."""
    source = TUTORIALS / "004_using_ray" / entrypoint
    shutil.copytree(source.parent, tmp_path, dirs_exist_ok=True)
    result = run_example([entrypoint], tmp_path)
    if entrypoint == "hello_ray.py":
        assert "Local process took" in result.stdout
        assert "Ray process took" in result.stdout
        with (tmp_path / "ray.csv").open() as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == 20
        assert all(row["timestamp"] for row in rows)
    else:
        assert "Process completed successfully!" in result.stdout
