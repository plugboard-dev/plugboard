"""Provides Components for interacting with LLMs."""

from __future__ import annotations

from abc import ABC
from collections import deque
from pydoc import locate
import typing as _t

from pydantic import BaseModel

from plugboard.component import Component, IOController as IO
from plugboard.schemas import ComponentArgsDict
from plugboard.utils import depends_on_optional


try:
    # Llama-index is an optional dependency
    from llama_index.core.base.llms.types import ImageBlock, TextBlock
    from llama_index.core.llms import LLM, ChatMessage, ChatResponse
except ImportError:  # pragma: no cover
    pass

if _t.TYPE_CHECKING:  # pragma: no cover
    from llama_index.core.llms import LLM


class _LLMBase(Component, ABC):
    """Internal base class providing shared LLM setup & structured output handling.

    Not exported; used to reduce duplication between `LLMChat` and `LLMImageProcessor`.
    """

    io = IO()

    def _initialize_llm(self, llm_str: str, llm_kwargs: _t.Optional[dict[str, _t.Any]]) -> LLM:
        _llm_cls = locate(llm_str)
        if _llm_cls is None or not isinstance(_llm_cls, type) or not issubclass(_llm_cls, LLM):
            raise ValueError(f"LLM class {llm_str} not found in llama-index.")
        llm_kwargs = llm_kwargs or {}
        return _llm_cls(**llm_kwargs)

    def _resolve_response_model(
        self, response_model: _t.Optional[_t.Type[BaseModel] | str]
    ) -> _t.Optional[_t.Type[BaseModel]]:
        if response_model is not None and isinstance(response_model, str):
            model = locate(response_model)
            if model is None or not isinstance(model, type) or not issubclass(model, BaseModel):
                raise ValueError(f"Response model {response_model} not found.")
            response_model = model
        return response_model

    def _apply_structured_response(
        self,
        llm: LLM,
        response_model: _t.Optional[_t.Type[BaseModel]],
        expand_response: bool,
    ) -> tuple[LLM, bool, bool]:
        structured = False
        expand = False
        if response_model is not None:
            structured = True
            llm = llm.as_structured_llm(output_cls=response_model)
            if expand_response:
                expand = True
                # Outputs replaced by model field names; caller must update io.outputs.
                self.io.outputs = list(response_model.model_fields.keys())
        return llm, structured, expand

    def _set_response(self, chat_response: ChatResponse, expand: bool) -> None:
        if not expand:
            self.response: str | None = chat_response.message.content
        else:
            for field, value in chat_response.raw.model_dump().items():  # type: ignore[union-attr]
                setattr(self, field, value)


class LLMChat(_LLMBase):
    """`LLMChat` is a component for interacting with large language models (LLMs).

    Requires the optional `plugboard[llm]` installation. The default LLM is OpenAI, and requires the
    `OPENAI_API_KEY` environment variable to be set. Other LLMs supported by llama-index can be
    used: see [here](https://docs.llamaindex.ai/en/stable/module_guides/models/llms/modules/) for
    available models. Additional llama-index dependencies may be required for specific models.

    Structured output is supported by providing a Pydantic model as the `response_model` argument.
    This can optionally be unpacked into individual output fields by setting `expand_response=True`,
    otherwise the LLM response will be stored in the `response` output field.
    """

    io = IO(inputs=["prompt"], outputs=["response"])

    @depends_on_optional("llama_index", "llm")
    def __init__(
        self,
        llm: str = "llama_index.llms.openai.OpenAI",
        system_prompt: _t.Optional[str] = None,
        context_window: int = 0,
        response_model: _t.Optional[_t.Type[BaseModel] | str] = None,
        expand_response: bool = False,
        llm_kwargs: _t.Optional[dict[str, _t.Any]] = None,
        **kwargs: _t.Unpack[ComponentArgsDict],
    ) -> None:
        """Instantiates `LLMChat`.

        Args:
            llm: The LLM class to use from llama-index.
            system_prompt: Optional; System prompt to prepend to the context window.
            context_window: The number of previous messages to include in the context window.
            response_model: Optional; A Pydantic model to structure the response. Can be specified
                as a string identifying the namespaced class to use.
            expand_response: Setting this to `True` when using a structured response model will
                cause the individual attributes of the response model to be added as output fields.
            llm_kwargs: Additional keyword arguments for the LLM.
            **kwargs: Additional keyword arguments for [`Component`][plugboard.component.Component].
        """
        super().__init__(**kwargs)
        self._llm: LLM = self._initialize_llm(llm, llm_kwargs)
        response_model = self._resolve_response_model(response_model)
        self._llm, self._structured, self._expand_response = self._apply_structured_response(
            self._llm, response_model, expand_response
        )
        self._memory: deque[ChatMessage] = deque(maxlen=context_window * 2)
        self._system_prompt = (
            [ChatMessage.from_str(role="system", content=system_prompt)] if system_prompt else []
        )

    async def step(self) -> None:  # noqa: D102
        if not self.prompt:
            return
        prompt_message = ChatMessage.from_str(role="user", content=str(self.prompt))
        full_prompt = [*self._system_prompt, *self._memory, prompt_message]
        response: ChatResponse = await self._llm.achat(full_prompt)
        self._memory.extend([prompt_message, response.message])

        self._set_response(response, self._expand_response)


class LLMImageProcessor(_LLMBase):
    """`LLMImageProcessor` processes an image with a vision-capable LLM.

    Sends a (optional) textual prompt plus an image to a llama-index LLM. The image may be
    provided either as a URL string (http/https or data URI) or as raw bytes. Structured output
    is supported via a Pydantic `response_model`.

    Inputs:
        image: Union[str, bytes]; if `str` treated as URL, if `bytes` passed directly via
            `ImageBlock(image=...)`.

    Outputs:
        response: Raw string response unless `expand_response=True` with a structured model.
        (If structured + expanded: individual model fields become outputs.)
    """

    io = IO(inputs=["image"], outputs=["response"])

    @depends_on_optional("llama_index", "llm")
    def __init__(
        self,
        llm: str = "llama_index.llms.openai.OpenAI",
        prompt: str | None = None,
        response_model: _t.Optional[_t.Type[BaseModel] | str] = None,
        expand_response: bool = False,
        llm_kwargs: _t.Optional[dict[str, _t.Any]] = None,
        **kwargs: _t.Unpack[ComponentArgsDict],
    ) -> None:
        """Instantiate `LLMImageProcessor`.

        Args:
            llm: The vision-capable LLM class path for llama-index.
            prompt: Optional; A base prompt applied to each request (can include instructions
                about desired output format, etc.).
            response_model: Optional; Pydantic model (or namespaced string) describing structured
                output expected from the LLM.
            expand_response: When using a structured response model, expands fields into outputs.
            llm_kwargs: Extra kwargs passed to the LLM constructor (e.g. {"model": "gpt-4o"}).
            **kwargs: Standard Component args.
        """
        super().__init__(**kwargs)
        self._llm: LLM = self._initialize_llm(llm, llm_kwargs)
        response_model = self._resolve_response_model(response_model)
        self._llm, self._structured, self._expand_response = self._apply_structured_response(
            self._llm, response_model, expand_response
        )
        self._prompt = prompt

    async def step(self) -> None:  # noqa: D102
        image_value = getattr(self, "image", None)
        if image_value is None:
            return

        blocks: list[TextBlock | ImageBlock] = []
        if self._prompt:
            blocks.append(TextBlock(text=self._prompt))

        image_block: ImageBlock
        if isinstance(image_value, bytes):
            image_block = ImageBlock(image=image_value)
        elif isinstance(image_value, str):
            # treat as URL/data URI/path; llama-index will fetch/handle accordingly if supported
            image_block = ImageBlock(image_url=image_value)
        else:  # pragma: no cover
            raise TypeError("`image` must be either bytes or str (URL/path)")

        blocks.append(image_block)

        prompt_message = ChatMessage(role="user", content=blocks)

        response: ChatResponse = await self._llm.achat([prompt_message])
        self._set_response(response, self._expand_response)
