"""Unit tests for LLM components."""

import json
import os
import typing as _t
from unittest.mock import patch

import openai_responses
from pydantic import BaseModel
import pytest

from plugboard.library.llm import LLMChat, LLMImageProcessor


class ExpectedResponse(BaseModel):  # noqa: D101
    x: int
    y: str


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


@pytest.mark.asyncio
@pytest.mark.parametrize("expand_response", [False, True])
@pytest.mark.parametrize(
    "response_model", [ExpectedResponse, "tests.unit.test_llm.ExpectedResponse"]
)
async def test_openai_structured_chat(
    openai_mock: openai_responses.OpenAIMock,
    expand_response: bool,
    response_model: _t.Type[BaseModel] | str,
) -> None:
    """Test the `LLMChat` component with structured output."""
    llm = LLMChat(
        name="llm",
        response_model=response_model,
        system_prompt="Help the user solve for x and y",
        expand_response=expand_response,
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
    if expand_response:
        # Response must be parsed
        assert llm.x == 45
        assert llm.y == "test"
    else:
        assert json.loads(llm.response) == test_response.model_dump()


@pytest.mark.asyncio
async def test_llm_image_processor(openai_mock: openai_responses.OpenAIMock) -> None:
    """Test the `LLMImageProcessor` component."""
    processor = LLMImageProcessor(
        name="processor",
        prompt="Describe this image",
        llm_kwargs={"model": "gpt-4o"},
    )
    await processor.init()

    openai_mock.chat.completions.create.response = {
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"content": "A beautiful landscape", "role": "assistant"},
            }
        ]
    }

    # Test with URL
    processor.image = "https://example.com/image.png"
    await processor.step()

    assert processor.response == "A beautiful landscape"

    request = json.loads(openai_mock.chat.completions.create.route.calls[-1].request.content)
    messages = request["messages"]
    assert len(messages) == 1
    content = messages[0]["content"]
    assert isinstance(content, list)
    # Check for text prompt
    assert any(
        block.get("type") == "text" and block.get("text") == "Describe this image"
        for block in content
    )
    # Check for image url
    assert any(
        block.get("type") == "image_url"
        and block.get("image_url", {}).get("url") == "https://example.com/image.png"
        for block in content
    )

    # Test with bytes
    # Note: llama-index converts bytes to base64 data URI
    processor.image = b"fakeimagebytes"
    await processor.step()
    assert processor.response == "A beautiful landscape"

    request = json.loads(openai_mock.chat.completions.create.route.calls[-1].request.content)
    messages = request["messages"]
    content = messages[0]["content"]
    # Check for image url with data uri
    image_block = next(block for block in content if block.get("type") == "image_url")
    assert image_block["image_url"]["url"].startswith("data:")
