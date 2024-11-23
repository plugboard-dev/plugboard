"""Provides Components for interacting with OpenAI-compatible models."""

from collections import deque
import typing as _t

from plugboard.component import Component, IOController as IO
from plugboard.exceptions import NotInitialisedError


try:
    from openai import AsyncAzureOpenAI, AsyncOpenAI
    from openai.types.chat import (
        ChatCompletionAssistantMessageParam,
        ChatCompletionMessageParam,
        ChatCompletionUserMessageParam,
    )
except ImportError:
    pass


class OpenAIChat(Component):
    """`OpenAIChat` provides a component for interacting with OpenAI-compatible models."""

    io = IO(inputs=["prompt"], outputs=["response"])

    def __init__(
        self,
        *args: _t.Any,
        model: str = "gpt-4o-turbo",
        system_prompt: _t.Optional[list[ChatCompletionMessageParam]] = None,
        context_window: int = 0,
        client_type: _t.Literal["openai", "azure"] = "openai",
        open_ai_kwargs: _t.Optional[dict[str, _t.Any]] = None,
        **kwargs: _t.Any,
    ) -> None:
        """Instantiates `OpenAIChat`.

        Args:
            *args: Additional positional arguments to pass to the underlying `Component`.
            model: The name of the model to use.
            system_prompt: Optional; The system prompt to use. See the OpenAI API documentation for
                examples.
            context_window: The number of messages to keep in the chat history. Higher values incur
                more token costs on each call.
            client_type: Whether to use "openai" or "azure" client.
            open_ai_kwargs: Optional; Dictionary of keyword arguments to pass to the underlying
                OpenAI client. Can include `base_url` to use a different OpenAI compatible API
                endpoint, e.g. Gemini.
            **kwargs: Additional keyword arguments to pass to the the underlying `Component`.
        """
        super().__init__(*args, **kwargs)
        self._model = model
        self._system_prompt: list[ChatCompletionMessageParam] = system_prompt or []
        # Store 2x the context window to allow for both input and output messages
        self._messages: deque[ChatCompletionMessageParam] = deque(maxlen=context_window * 2)
        self._open_ai_kwargs = open_ai_kwargs or {}
        self._client_type = client_type
        self._client: _t.Optional[AsyncOpenAI | AsyncAzureOpenAI] = None

    async def init(self) -> None:  # noqa: D102
        if self._client_type == "azure":
            self._client = AsyncAzureOpenAI(**self._open_ai_kwargs)
        else:
            self._client = AsyncOpenAI(**self._open_ai_kwargs)

    async def step(self) -> None:  # noqa: D102
        if not self._client:
            raise NotInitialisedError()
        messages = [
            *self._system_prompt,
            *self._messages,
            ChatCompletionUserMessageParam(
                role="user",
                content=self.prompt,  # type: ignore
            ),
        ]
        completion = await self._client.chat.completions.create(
            messages=messages,
            model=self._model,
        )
        response = completion.choices[0].message.content
        if response is not None:
            self._messages.extend(
                [
                    ChatCompletionUserMessageParam(
                        role="user",
                        content=self.prompt,  # type: ignore
                    ),
                    ChatCompletionAssistantMessageParam(
                        role="assistant",
                        content=response,
                    ),
                ],
            )
        self.response = response  # type: ignore
