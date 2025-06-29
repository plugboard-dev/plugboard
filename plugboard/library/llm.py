"""Provides Components for interacting with LLMs."""

from __future__ import annotations

from collections import deque
from pydoc import locate
import typing as _t

from pydantic import BaseModel

from plugboard.component import Component, IOController as IO
from plugboard.schemas import ComponentArgsDict
from plugboard.utils import depends_on_optional


try:
    # Llama-index is an optional dependency
    from llama_index.core.llms import LLM, ChatMessage, ChatResponse
except ImportError:
    pass

if _t.TYPE_CHECKING:  # pragma: no cover
    from llama_index.core.llms import LLM


class LLMChat(Component):
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
        self._structured = False
        self._expand_response = False
        if response_model is not None:
            self._structured = True
            self._llm = self._llm.as_structured_llm(output_cls=response_model)
            if expand_response:
                self._expand_response = True
                self.io.outputs = list(response_model.model_fields.keys())
        self._memory: deque[ChatMessage] = deque(maxlen=context_window * 2)
        self._system_prompt = (
            [ChatMessage.from_str(role="system", content=system_prompt)] if system_prompt else []
        )

    def _initialize_llm(self, llm_str: str, llm_kwargs: _t.Optional[dict[str, _t.Any]]) -> LLM:
        """Initializes the LLM from the given class name and keyword arguments."""
        _llm_cls = locate(llm_str)
        if _llm_cls is None or not isinstance(_llm_cls, type) or not issubclass(_llm_cls, LLM):
            raise ValueError(f"LLM class {llm_str} not found in llama-index.")
        llm_kwargs = llm_kwargs or {}
        return _llm_cls(**llm_kwargs)

    def _resolve_response_model(
        self, response_model: _t.Optional[_t.Type[BaseModel] | str]
    ) -> _t.Optional[_t.Type[BaseModel]]:
        """Resolves the response model from a class or string."""
        if response_model is not None and isinstance(response_model, str):
            model = locate(response_model)
            if model is None or not isinstance(model, type) or not issubclass(model, BaseModel):
                raise ValueError(f"Response model {response_model} not found.")
            response_model = model
        return response_model

    async def step(self) -> None:  # noqa: D102
        if not self.prompt:
            return
        prompt_message = ChatMessage.from_str(role="user", content=str(self.prompt))
        full_prompt = [*self._system_prompt, *self._memory, prompt_message]
        response: ChatResponse = await self._llm.achat(full_prompt)
        self._memory.extend([prompt_message, response.message])
        if not self._expand_response:
            self.response: str | None = response.message.content
        else:
            for field, value in response.raw.model_dump().items():  # type: ignore[union-attr]
                setattr(self, field, value)
