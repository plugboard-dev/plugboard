"""Unit tests for the `FileReader` and `FileWriter` components."""

import os
import tempfile
import typing as _t
import uuid

import fsspec
from moto.moto_server.threaded_moto_server import ThreadedMotoServer
import pandas as pd
import pytest

from plugboard.connector import AsyncioConnector
from plugboard.exceptions import IOStreamClosedError
from plugboard.library.file_io import FileReader, FileWriter
from plugboard.schemas import ConnectorSpec


S3_IP_ADDRESS = "127.0.0.1"
S3_PORT = 45454
S3_URL = f"http://{S3_IP_ADDRESS}:{S3_PORT}"


@pytest.fixture(scope="module", autouse=True)
def mock_s3_server() -> _t.Generator[None, None, None]:
    """Provides a mock S3 server for testing.

    Required for async tests until this is resolved:
        https://github.com/aio-libs/aiobotocore/issues/755
    """
    server = ThreadedMotoServer(ip_address=S3_IP_ADDRESS, port=S3_PORT)
    server.start()
    if "AWS_SECRET_ACCESS_KEY" not in os.environ:
        os.environ["AWS_SECRET_ACCESS_KEY"] = "test-access-key"  # noqa: S105
    if "AWS_ACCESS_KEY_ID" not in os.environ:
        os.environ["AWS_ACCESS_KEY_ID"] = "test-key-id"
    if "AWS_ENDPOINT_URL" not in os.environ:
        os.environ["AWS_ENDPOINT_URL"] = S3_URL

    yield
    server.stop()


@pytest.fixture
def df() -> pd.DataFrame:
    """DataFrame for testing read/write."""
    return pd.DataFrame(
        {"x": [1, 2, 3, 4, 5], "y": [6, 7, 8, 9, 10], "z": ["a", "b", "c", "d", "e"]}
    )


@pytest.fixture(scope="module", params=["local", "s3"])
def temp_location(request: pytest.FixtureRequest) -> _t.Generator[str, None, None]:
    """Temporary file location."""
    if request.param == "local":
        with tempfile.TemporaryDirectory() as temp_dir:
            yield os.path.join(temp_dir, "")
    elif request.param == "s3":
        fs = fsspec.filesystem("s3")
        fs.mkdir("s3://test-bucket/")
        yield "s3://test-bucket/"
    else:
        raise ValueError(f"Unsupported storage type: {request.param}")


@pytest.fixture(params=[".csv", ".csv.gz", ".parquet"])
def read_path(
    df: pd.DataFrame, temp_location: str, request: pytest.FixtureRequest
) -> _t.Generator[str, None, None]:
    """File path for reading."""
    path = f"{temp_location}test{request.param}"
    if request.param == ".csv":
        df.to_csv(path, index=False)
    elif request.param == ".csv.gz":
        df.to_csv(path, index=False, compression="gzip")
    elif request.param == ".parquet":
        df.to_parquet(path)
    else:
        raise ValueError(f"Unsupported file format: {request.param}")
    yield path


@pytest.fixture(params=[".csv", ".csv.gz", ".parquet"])
def write_path(temp_location: str, request: pytest.FixtureRequest) -> _t.Generator[str, None, None]:
    """File path for reading."""
    path = f"{temp_location}{uuid.uuid4().hex}{request.param}"
    yield path


@pytest.mark.asyncio
@pytest.mark.parametrize("chunk_size", [None, 2, 4, 10])
async def test_file_reader(df: pd.DataFrame, read_path: str, chunk_size: _t.Optional[int]) -> None:
    """Test the `FileReader` component."""
    reader = FileReader(
        name="file-reader", path=read_path, field_names=list(df.columns), chunk_size=chunk_size
    )
    await reader.init()

    # Each row of data must be read correctly
    for _, row in df.iterrows():
        await reader.step()
        for field in df.columns:
            assert getattr(reader, field) == row[field]

    # There must be no more data to read
    with pytest.raises(IOStreamClosedError):
        await reader.step()


@pytest.mark.asyncio
@pytest.mark.parametrize("chunk_size", [None, 2, 4, 10])
async def test_file_writer(df: pd.DataFrame, write_path: str, chunk_size: _t.Optional[int]) -> None:
    """Test the `FileWriter` component."""
    if write_path.endswith(".parquet") and chunk_size:
        pytest.skip("Parquet does not support chunked writing")
    writer = FileWriter(
        name="file-writer",
        path=write_path,
        field_names=list(df.columns),
        chunk_size=chunk_size,
    )
    connectors = {
        field: AsyncioConnector(
            spec=ConnectorSpec(source="none.none", target=f"file-writer.{field}"),
        )
        for field in df.columns
    }
    await writer.io.connect(list(connectors.values()))

    await writer.init()

    output_channels = {field: await connectors[field].connect_send() for field in df.columns}
    for _, row in df.iterrows():
        for field in df.columns:
            await output_channels[field].send(row[field])
        await writer.step()

    await writer.io.close()
    await writer.run()

    # Saved data must match the original dataframe
    df_saved = (
        pd.read_parquet(write_path) if write_path.endswith(".parquet") else pd.read_csv(write_path)
    )
    pd.testing.assert_frame_equal(df_saved, df)
