"""Unit tests for OpenAI components."""

import json
import os
import typing as _t
from unittest.mock import patch

import openai_responses
import pytest

from plugboard.connector import AsyncioChannel, Connector
from plugboard.library.openai import OpenAIChat
from plugboard.schemas import ConnectorSpec


@pytest.fixture(params=["openai", "azure"])
def client_type(request: pytest.FixtureRequest) -> _t.Iterator[str]:
    """Client type for OpenAI."""
    if request.param == "openai":
        patch_environ = {"OPENAI_API_KEY": f"test-{request.param}-key"}
    elif request.param == "azure":
        patch_environ = {
            "AZURE_OPENAI_API_KEY": f"test-{request.param}-key",
            "OPENAI_API_VERSION": "2024-02-01",
            "AZURE_OPENAI_ENDPOINT": "https://example-endpoint.openai.azure.com",
        }
    with patch.dict(os.environ, patch_environ):
        yield request.param


@pytest.fixture
def openai_mock(client_type: str) -> _t.Iterator[openai_responses.OpenAIMock]:
    """Mock OpenAI API."""
    if client_type == "openai":
        args = {}
    elif client_type == "azure":
        args = {"base_url": "https://example-endpoint.openai.azure.com"}
    mock = openai_responses.OpenAIMock(**args)
    with mock.router:
        yield mock


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "system_prompt, context_window",
    [
        (
            [],
            0,
        ),
        (
            [{"role": "system", "content": "You are a helpful assistant"}],
            2,
        ),
    ],
)
async def test_openai_chat(
    openai_mock: openai_responses.OpenAIMock, system_prompt, context_window: int, client_type: str
) -> None:
    """Test the `OpenAIChat` component."""
    llm = OpenAIChat(
        name="llm",
        system_prompt=system_prompt,
        context_window=context_window,
        client_type=client_type,
    )
    conn = Connector(
        spec=ConnectorSpec(source="none.none", target="llm.prompt"),
        channel=AsyncioChannel(),
    )

    llm.io.connect([conn])
    await llm.init()

    for message_id in range(5):
        openai_mock.chat.completions.create.response = {
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"content": f"Test response {message_id}", "role": "assistant"},
                }
            ]
        }
        await conn.channel.send(f"Test prompt {message_id}")
        await llm.step()
        request = json.loads(openai_mock.chat.completions.create.route.calls[-1].request.content)
        # Response must be set correctly on the component
        assert llm.response == f"Test response {message_id}"
        # Request must contain the correct messages: 1 system prompt, context window, prompt
        assert (
            len(request["messages"]) == len(system_prompt) + min(message_id, context_window) * 2 + 1
        )
        if system_prompt:
            assert request["messages"][0]["role"] == "system"
        else:
            assert request["messages"][0]["role"] == "user"
        if context_window & message_id > 0:
            assert request["messages"][-3]["role"] == "user"
            assert request["messages"][-2]["role"] == "assistant"
