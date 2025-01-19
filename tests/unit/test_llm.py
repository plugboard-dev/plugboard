"""Unit tests for LLM components."""

import json
import os
import typing as _t
from unittest.mock import patch

import openai_responses
from pydantic import BaseModel
import pytest

from plugboard.library.llm import LLMChat


@pytest.fixture
def openai_mock() -> _t.Iterator[openai_responses.OpenAIMock]:
    """Mock OpenAI API."""
    patch_environ = {"OPENAI_API_KEY": "test-openai-key"}
    with patch.dict(os.environ, patch_environ):
        mock = openai_responses.OpenAIMock()
        with mock.router:
            yield mock


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "system_prompt, context_window",
    [
        (
            None,
            0,
        ),
        (
            "You are an LLM chatbot.",
            2,
        ),
    ],
)
async def test_llm_chat(
    openai_mock: openai_responses.OpenAIMock,
    system_prompt: _t.Optional[str],
    context_window: int,
) -> None:
    """Test the `LLMChat` component."""
    llm = LLMChat(
        name="llm",
        system_prompt=system_prompt,
        context_window=context_window,
        llm_kwargs={"model": "gpt-4o-mini"},
    )
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
        llm.prompt = f"Test prompt {message_id}"
        await llm.step()
        request = json.loads(openai_mock.chat.completions.create.route.calls[-1].request.content)
        # Response must be set correctly on the component
        assert llm.response == f"Test response {message_id}"
        # Request must contain the correct messages: 1 system prompt, context window, prompt
        assert (
            len(request["messages"])
            == (1 if system_prompt else 0) + min(message_id, context_window) * 2 + 1
        )
        if system_prompt:
            assert request["messages"][0]["role"] == "system"
        else:
            assert request["messages"][0]["role"] == "user"
        if context_window & message_id > 0:
            assert request["messages"][-3]["role"] == "user"
            assert request["messages"][-2]["role"] == "assistant"


async def test_openai_structured_chat(
    openai_mock: openai_responses.OpenAIMock,
) -> None:
    """Test the `LLMChat` component with structured output."""

    class ExpectedResponse(BaseModel):
        x: int
        y: str

    llm = LLMChat(
        name="llm",
        response_model=ExpectedResponse,
        system_prompt="Help the user solve for x and y",
        llm_kwargs={"model": "gpt-4o-mini"},
    )
    await llm.init()

    test_response = ExpectedResponse(x=45, y="test")
    openai_mock.chat.completions.create.response = {
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "content": test_response.model_dump_json(),
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_abc123",
                            "type": "function",
                            "function": {
                                "name": "ExpectedResponse",
                                "arguments": '{"x": 45, "y": "test"}',
                            },
                        }
                    ],
                },
            }
        ]
    }
    llm.prompt = "Test prompt"
    await llm.step()
    # Response must be parsed
    assert llm.x == 45
    assert llm.y == "test"
    assert json.loads(llm.response) == test_response.model_dump()
