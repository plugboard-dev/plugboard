"""Provides Components for interacting with OpenAI-compatible models."""

from abc import ABC, abstractmethod
from collections import deque
import typing as _t

from plugboard.component import Component, IOController as IO
from plugboard.exceptions import NotInitialisedError


try:
    # OpenAI is an optional dependency
    from openai import AsyncAzureOpenAI, AsyncOpenAI
    from openai.types.chat import (
        ChatCompletionAssistantMessageParam,
        ChatCompletionMessageParam,
        ChatCompletionUserMessageParam,
    )
except ImportError:
    pass


class _OpenAIBase(Component, ABC):
    """Base class for OpenAI Components."""

    io = IO(inputs=["prompt"], outputs=["response"])

    def __init__(
        self,
        *args: _t.Any,
        model: str = "gpt-4o-mini",
        system_prompt: _t.Optional[list[ChatCompletionMessageParam]] = None,
        context_window: int = 0,
        client_type: _t.Literal["openai", "azure"] = "openai",
        open_ai_kwargs: _t.Optional[dict[str, _t.Any]] = None,
        **kwargs: _t.Any,
    ) -> None:
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

    @abstractmethod
    async def step(self) -> None:  # noqa: D102
        if not self._client:
            raise NotInitialisedError()


class OpenAIChat(_OpenAIBase):
    """`OpenAIChat` provides a component for interacting with OpenAI-compatible models.

    Requires the optional `plugboard[openai]` installation. The API key can be set via the
    `OPENAI_API_KEY` environment variable. For Azure OpenAI, use `AZURE_OPENAI_API_KEY` and
    see [here](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/switching-endpoints)
    for additional configuration options.

    See the [OpenAI docs](https://platform.openai.com/docs/quickstart?language-preference=python)
    for more information on configuration and message types.
    """

    io = IO(inputs=["prompt"], outputs=["response"])

    def __init__(
        self,
        *args: _t.Any,
        model: str = "gpt-4o-mini",
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
            system_prompt: Optional; A list of prompts to provide to the model. This can include a
                system prompt, along with user and assistant messages. Each message should contain
                a `role` and `content` field. See the OpenAI docs for more information.
            context_window: The number of messages to keep in the chat history. Higher values incur
                more token costs on each call.
            client_type: Whether to use "openai" or "azure" client.
            open_ai_kwargs: Optional; Dictionary of keyword arguments to pass to the underlying
                OpenAI client. Can include `base_url` to use a different OpenAI compatible API
                endpoint, e.g. Gemini.
            **kwargs: Additional keyword arguments to pass to the the underlying `Component`.
        """
        super().__init__(
            *args,
            model=model,
            system_prompt=system_prompt,
            context_window=context_window,
            client_type=client_type,
            open_ai_kwargs=open_ai_kwargs,
            **kwargs,
        )

    async def step(self) -> None:  # noqa: D102
        await super().step()
        if not self._client:
            raise NotInitialisedError()
        completion = await self._client.chat.completions.create(
            messages=[
                *self._system_prompt,
                *self._messages,
                ChatCompletionUserMessageParam(
                    role="user",
                    content=self.prompt,  # type: ignore
                ),
            ],
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
