"""Provides Components for interacting with LLMs."""

from collections import deque
from pydoc import locate
import typing as _t

from pydantic import BaseModel

from plugboard.component import Component, IOController as IO
from plugboard.utils import depends_on_optional


try:
    # Llama-index is an optional dependency
    from llama_index.core.llms import LLM, ChatMessage
except ImportError:
    pass


class LLMChat(Component):
    """`LLMChat` is a component for interacting with large language models (LLMs).

    Requires the optional `plugboard[llm]` installation. The default LLM is OpenAI, and requires the
    `OPENAI_API_KEY` environment variable to be set. Other LLMs supported by llama-index can be
    used: see [here](https://docs.llamaindex.ai/en/stable/module_guides/models/llms/modules/) for
    available models. Additional llama-index dependencies may be required for specific models.
    """

    io = IO(inputs=["prompt"], outputs=["response"])

    @depends_on_optional("llm")
    def __init__(
        self,
        name: str,
        llm: str = "llama_index.llms.openai.OpenAI",
        system_prompt: _t.Optional[str] = None,
        context_window: int = 0,
        response_model: _t.Optional[_t.Type[BaseModel]] = None,
        llm_kwargs: _t.Optional[dict[str, _t.Any]] = None,
    ) -> None:
        """Instantiates `LLMChat`.

        Args:
            name: The name of the component.
            llm: The LLM class to use from llama-index.
            system_prompt: Optional; System prompt to prepend to the context window.
            context_window: The number of previous messages to include in the context window.
            response_model: Optional; A Pydantic model to structure the response.
            llm_kwargs: Additional keyword arguments for the LLM.
        """
        super().__init__(name=name)
        _llm_cls = locate(llm)
        if _llm_cls is None or not issubclass(_llm_cls, LLM):
            raise ValueError(f"LLM class {llm} not found in llama-index.")
        self._llm = _llm_cls(**llm_kwargs)
        self._structured = response_model is not None
        if response_model is not None:
            self.io = IO(
                inputs=["prompt"], outputs=["response", *response_model.City.model_fields.keys()]
            )
            self._llm = self._llm.as_structured_llm(output_cls=response_model)
        # Memory 2x context window size for both prompt and response
        self._memory: deque[ChatMessage] = deque(maxlen=context_window * 2)
        self._system_prompt = ChatMessage.from_str(role="system", content=system_prompt)

    async def step(self) -> None:  # noqa: D102
        if not self.prompt:
            return
        full_prompt = [
            self._system_prompt,
            *list(self._memory),
            ChatMessage.from_str(role="user", content=self.prompt),
        ]
        response = await self._engine.achat(full_prompt)
        self._memory.append(response.message)
        self.response = response.message.content
        if self._structured:
            for field, value in response.raw.model_dump().items():
                setattr(self, field, value)
