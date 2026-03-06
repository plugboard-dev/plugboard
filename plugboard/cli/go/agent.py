"""Copilot SDK agent integration for Plugboard Go."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
import typing as _t

from copilot import CopilotClient, CopilotSession, PermissionHandler

from plugboard.cli.go.tools import (
    create_mermaid_diagram_tool,
    create_run_model_tool,
)


_FALLBACK_SYSTEM_PROMPT = (
    "You are a helpful assistant that helps users design and implement "
    "Plugboard models. Plugboard is an event-driven modelling framework "
    "in Python."
)


def _load_system_prompt() -> str:
    """Load the system prompt from bundled package data.

    The AGENTS.md file is shipped inside the ``plugboard.cli.go`` package
    so that it is available even when plugboard is installed from a wheel.
    Falls back to ``examples/AGENTS.md`` in the working directory for
    local development, or to a short built-in prompt if neither is found.
    """
    # 1. Load from package data (works in installed wheels)
    try:
        ref = resources.files("plugboard.cli.go").joinpath("AGENTS.md")
        text = ref.read_text(encoding="utf-8")
        if text:
            return text
    except (FileNotFoundError, TypeError, ModuleNotFoundError):
        pass

    # 2. Fallback for local dev: check examples/ in the working directory
    cwd_candidate = Path.cwd() / "examples" / "AGENTS.md"
    if cwd_candidate.exists():
        return cwd_candidate.read_text(encoding="utf-8")

    return _FALLBACK_SYSTEM_PROMPT


class PlugboardAgent:
    """Manages the Copilot client and session for the Plugboard Go TUI."""

    def __init__(
        self,
        model: str,
        on_assistant_delta: _t.Callable[[str], None] | None = None,
        on_assistant_message: _t.Callable[[str], None] | None = None,
        on_tool_start: _t.Callable[[str], None] | None = None,
        on_user_input_request: _t.Callable[[dict, dict], _t.Awaitable[dict]] | None = None,
        on_mermaid_url: _t.Callable[[str], None] | None = None,
        on_idle: _t.Callable[[], None] | None = None,
    ) -> None:
        self._model = model
        self._on_assistant_delta = on_assistant_delta
        self._on_assistant_message = on_assistant_message
        self._on_tool_start = on_tool_start
        self._on_user_input_request_cb = on_user_input_request
        self._on_mermaid_url = on_mermaid_url
        self._on_idle = on_idle
        self._client: CopilotClient | None = None
        self._session: CopilotSession | None = None

    @property
    def model(self) -> str:
        """Return the current model name."""
        return self._model

    async def start(self) -> None:
        """Start the Copilot client and create a session."""
        self._client = CopilotClient({"log_level": "error"})
        await self._client.start()

        system_prompt = _load_system_prompt()

        tools = [
            create_run_model_tool(),
            create_mermaid_diagram_tool(on_url_generated=self._on_mermaid_url),
        ]

        session_config: dict[str, _t.Any] = {
            "model": self._model,
            "streaming": True,
            "tools": tools,
            "system_message": {
                "content": system_prompt,
            },
            "on_permission_request": PermissionHandler.approve_all,
        }

        if self._on_user_input_request_cb is not None:
            session_config["on_user_input_request"] = self._on_user_input_request_cb

        self._session = await self._client.create_session(session_config)
        self._session.on(self._handle_event)

    def _handle_event(self, event: _t.Any) -> None:
        """Route session events to callbacks."""
        event_type = event.type.value if hasattr(event.type, "value") else str(event.type)

        if event_type == "assistant.message_delta":
            delta = event.data.delta_content or ""
            if delta and self._on_assistant_delta:
                self._on_assistant_delta(delta)
        elif event_type == "assistant.message":
            content = event.data.content or ""
            if self._on_assistant_message:
                self._on_assistant_message(content)
        elif event_type == "tool.execution_start":
            tool_name = event.data.tool_name if hasattr(event.data, "tool_name") else "unknown"
            if self._on_tool_start:
                self._on_tool_start(tool_name)
        elif event_type == "session.idle":
            if self._on_idle:
                self._on_idle()

    async def send(self, prompt: str) -> None:
        """Send a user prompt to the agent."""
        if self._session is None:
            raise RuntimeError("Agent not started. Call start() first.")
        await self._session.send({"prompt": prompt})

    async def list_models(self) -> list[str]:
        """List available models."""
        if self._client is None:
            raise RuntimeError("Agent not started. Call start() first.")
        try:
            models = await self._client.list_models()
            return [m.id for m in models] if models else []
        except Exception:
            return ["gpt-4o", "gpt-5", "claude-sonnet-4", "claude-sonnet-4-thinking", "o3"]

    async def change_model(self, model: str) -> None:
        """Change the model by destroying and recreating the session."""
        self._model = model
        if self._session is not None:
            await self._session.destroy()
        if self._client is not None:
            system_prompt = _load_system_prompt()
            tools = [
                create_run_model_tool(),
                create_mermaid_diagram_tool(on_url_generated=self._on_mermaid_url),
            ]
            session_config: dict[str, _t.Any] = {
                "model": self._model,
                "streaming": True,
                "tools": tools,
                "system_message": {
                    "content": system_prompt,
                },
                "on_permission_request": PermissionHandler.approve_all,
            }
            if self._on_user_input_request_cb is not None:
                session_config["on_user_input_request"] = self._on_user_input_request_cb
            self._session = await self._client.create_session(session_config)
            self._session.on(self._handle_event)

    async def stop(self) -> None:
        """Clean up the Copilot client and session."""
        if self._session is not None:
            try:
                await self._session.destroy()
            except Exception:  # noqa: S110
                pass  # Best-effort cleanup
            self._session = None
        if self._client is not None:
            try:
                await self._client.stop()
            except Exception:  # noqa: S110
                pass  # Best-effort cleanup
            self._client = None
