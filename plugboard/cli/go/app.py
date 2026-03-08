"""Textual TUI application for Plugboard Go."""

from __future__ import annotations

import asyncio
from pathlib import Path
import typing as _t

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import (
    DirectoryTree,
    Header,
    Input,
    Markdown,
    OptionList,
    Static,
)
from textual.widgets.option_list import Option

from plugboard import __version__
from plugboard.cli.go.agent import PlugboardAgent
from plugboard.utils.theme import PlugboardTheme as Theme


if _t.TYPE_CHECKING:
    from copilot.types import UserInputRequest

from copilot.types import UserInputResponse


def _theme_css(css: str) -> str:
    """Substitute theme color placeholders into Textual CSS."""
    return (
        css.replace("__PB_BLUE__", Theme.PB_BLUE)
        .replace("__PB_BLACK__", Theme.PB_BLACK)
        .replace("__PB_GRAY__", Theme.PB_GRAY)
        .replace("__PB_ACCENT1__", Theme.PB_ACCENT1)
        .replace("__PB_ACCENT2__", Theme.PB_ACCENT2)
        .replace("__PB_ACCENT3__", Theme.PB_ACCENT3)
        .replace("__PB_WHITE__", Theme.PB_WHITE)
        .replace("__PB_PINK__", Theme.PB_PINK)
    )


# -- Custom Messages ---------------------------------------------------------


class AgentDelta(Message):
    """Streaming text delta from the assistant."""

    def __init__(self, delta: str) -> None:
        super().__init__()
        self.delta = delta


class AgentMessage(Message):
    """Complete assistant message."""

    def __init__(self, content: str) -> None:
        super().__init__()
        self.content = content


class AgentToolStart(Message):
    """Tool execution started."""

    def __init__(self, tool_name: str) -> None:
        super().__init__()
        self.tool_name = tool_name


class AgentQuestion(Message):
    """Agent is asking the user a question."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class AgentMermaidUrl(Message):
    """New mermaid diagram URL generated."""

    def __init__(self, url: str) -> None:
        super().__init__()
        self.url = url


class AgentIdle(Message):
    """Agent session went idle."""


class AgentStatus(Message):
    """System status message."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


# -- Custom Widgets ----------------------------------------------------------


class ChatMessage(Static):
    """A single chat message displayed in the conversation."""

    DEFAULT_CSS = _theme_css("""
    ChatMessage {
        padding: 0 2;
        margin: 0;
    }
    ChatMessage.user {
        background: __PB_BLACK__;
        border-left: thick __PB_BLUE__;
        color: __PB_WHITE__;
    }
    ChatMessage.assistant {
        background: __PB_ACCENT3__;
        border-left: thick __PB_ACCENT1__;
        color: __PB_WHITE__;
    }
    ChatMessage.system {
        background: __PB_BLACK__;
        border-left: thick __PB_ACCENT3__;
        color: __PB_GRAY__;
    }
    ChatMessage .message-header {
        margin: 0;
        padding: 0;
    }
    ChatMessage .message-body {
        margin: 0;
        padding: 0;
    }
    """)

    def __init__(
        self,
        content: str,
        role: str = "assistant",
        **kwargs: _t.Any,
    ) -> None:
        super().__init__(**kwargs)
        self._role = role
        self._content: str = content.rstrip()
        self.add_class(role)

    @property
    def role(self) -> str:
        """Return the message role."""
        return self._role

    @property
    def content(self) -> str:
        """Return the message content."""
        return self._content

    def compose(self) -> ComposeResult:
        """Compose the chat message widget."""
        if self._role == "user":
            label = "You"
        elif self._role == "system":
            label = "System"
        else:
            label = "Copilot"
        yield Static(
            f"[bold]{label}[/bold]",
            classes="message-header",
        )
        yield Markdown(self._content, classes="message-body")

    def append_content(self, delta: str) -> None:
        """Append streaming content to the message body."""
        self._content = f"{self._content}{delta}".rstrip()
        try:
            md = self.query_one(".message-body", Markdown)
            md.update(self._content)
        except NoMatches:
            pass

    def replace_content(self, content: str) -> None:
        """Replace the message content."""
        self._content = content.rstrip()
        try:
            md = self.query_one(".message-body", Markdown)
            md.update(self._content)
        except NoMatches:
            pass


class ModelSelector(Static):
    """Displays selected model and allows changing it."""

    DEFAULT_CSS = _theme_css("""
    ModelSelector {
        dock: top;
        height: 1;
        padding: 0 1;
        background: __PB_BLUE__;
        color: __PB_WHITE__;
        text-style: bold;
    }
    """)

    model_name: reactive[str] = reactive("gpt-4o")

    def render(self) -> str:
        """Render the model selector."""
        return f"Model: {self.model_name}  (press [bold]m[/bold] to change)"


class MermaidLink(Static):
    """Displays a link to the mermaid diagram."""

    DEFAULT_CSS = _theme_css("""
    MermaidLink {
        height: auto;
        padding: 0 1;
        background: __PB_BLUE__;
        color: __PB_WHITE__;
    }
    """)

    url: reactive[str] = reactive("")

    def render(self) -> str:
        """Render the mermaid diagram link."""
        if self.url:
            return f"Diagram: {self.url}"
        return "No diagram generated yet"


class TitleBanner(Static):
    """Displays the Plugboard title and version."""

    DEFAULT_CSS = _theme_css("""
    TitleBanner {
        dock: top;
        height: 4;
        padding: 1 2 0 2;
        background: __PB_BLUE__;
        color: __PB_WHITE__;
        content-align: center middle;
    }
    """)

    def render(self) -> str:
        """Render the title banner."""
        return f"[bold {Theme.PB_ACCENT1}]P L U G B O A R D[/]\n[{Theme.PB_GRAY}]v{__version__}[/]"


# -- Model Selection Screen --------------------------------------------------


class ModelSelectionOverlay(VerticalScroll):
    """Overlay for selecting a model."""

    DEFAULT_CSS = _theme_css("""
    ModelSelectionOverlay {
        dock: top;
        layer: overlay;
        width: 60;
        max-height: 20;
        margin: 3 5;
        padding: 1 2;
        background: __PB_BLACK__;
        color: __PB_WHITE__;
        border: thick __PB_ACCENT1__;
    }
    """)

    def compose(self) -> ComposeResult:
        """Compose the model selection overlay."""
        yield Static(
            "[bold]Select a model[/bold]\n",
            id="model-title",
        )
        yield OptionList(id="model-list")

    def set_models(
        self,
        models: list[str],
        current: str,
    ) -> None:
        """Populate the model list."""
        option_list = self.query_one("#model-list", OptionList)
        option_list.clear_options()
        for m in models:
            label = f"* {m} (current)" if m == current else f"  {m}"
            option_list.add_option(Option(label, id=m))


# -- Main Application --------------------------------------------------------


class PlugboardGoApp(App[None]):
    """Plugboard Go - Interactive AI model builder."""

    TITLE = "Plugboard Go"
    SUB_TITLE = f"v{__version__}"

    CSS = _theme_css("""
    Screen {
        background: __PB_BLACK__;
        color: __PB_WHITE__;
    }

    Header {
        background: __PB_BLUE__;
        color: __PB_WHITE__;
        border-bottom: solid __PB_ACCENT1__;
    }

    #shortcut-hint {
        height: auto;
        padding: 0 1;
        background: __PB_BLUE__;
        color: __PB_WHITE__;
        border-top: solid __PB_ACCENT1__;
    }

    #title-banner {
        dock: top;
        height: 4;
        padding: 1 2 0 2;
        background: __PB_BLUE__;
        color: __PB_WHITE__;
        text-align: center;
        content-align: center middle;
        text-style: bold;
    }

    #main-container {
        width: 1fr;
        height: 1fr;
    }

    #chat-panel {
        width: 3fr;
        height: 1fr;
        background: __PB_BLACK__;
    }

    #sidebar {
        width: 1fr;
        min-width: 30;
        max-width: 50;
        height: 1fr;
        border-left: thick __PB_ACCENT1__;
        background: __PB_ACCENT3__;
    }

    #chat-scroll {
        height: 1fr;
        background: __PB_BLACK__;
    }

    #chat-input {
        margin: 0 1;
        background: __PB_BLACK__;
        border: solid __PB_BLUE__;
        color: __PB_WHITE__;
    }

    #file-tree-label {
        padding: 0 1;
        text-style: bold;
        background: __PB_BLUE__;
        color: __PB_WHITE__;
    }

    DirectoryTree {
        height: 1fr;
        background: __PB_ACCENT3__;
        color: __PB_WHITE__;
    }

    ModelSelectionOverlay {
        display: none;
    }

    ModelSelectionOverlay.visible {
        display: block;
    }
    """)

    BINDINGS = [
        Binding(
            "m",
            "select_model",
            "Change Model",
            show=True,
        ),
        Binding("q", "quit", "Quit", show=True),
    ]

    model_name: reactive[str] = reactive("gpt-4o")
    mermaid_url: reactive[str] = reactive("")

    def __init__(
        self,
        model_name: str = "gpt-4o",
        **kwargs: _t.Any,
    ) -> None:
        super().__init__(**kwargs)
        self.model_name = model_name
        self._agent: PlugboardAgent | None = None
        self._current_assistant_msg: ChatMessage | None = None
        self._user_input_future: asyncio.Future[UserInputResponse] | None = None
        self._waiting_for_user_input = False

    def compose(self) -> ComposeResult:
        """Compose the main application layout."""
        welcome = (
            "Welcome to **Plugboard Go**! I'm your AI "
            "assistant powered by GitHub Copilot. Tell me "
            "what model you'd like to build and I'll help "
            "you design, implement, and run it.\n\nDescribe "
            "your model at a high level and I'll help you "
            "plan the components, connections, and data flow."
        )
        yield Header()
        yield TitleBanner(id="title-banner")
        yield ModelSelector(id="model-selector")
        with Horizontal(id="main-container"):
            with Vertical(id="chat-panel"):
                with VerticalScroll(id="chat-scroll"):
                    yield ChatMessage(welcome, role="system")
                yield MermaidLink(id="mermaid-link")
                yield Static(
                    "[bold]q[/bold] Quit   [bold]m[/bold] Change Model",
                    id="shortcut-hint",
                )
                yield Input(
                    placeholder="Describe your model...",
                    id="chat-input",
                )
            with Vertical(id="sidebar"):
                yield Static("Files", id="file-tree-label")
                yield DirectoryTree(
                    str(Path.cwd()),
                    id="file-tree",
                )
        yield ModelSelectionOverlay(id="model-overlay")

    async def on_mount(self) -> None:
        """Start up the Copilot agent when the app mounts."""
        selector = self.query_one(
            "#model-selector",
            ModelSelector,
        )
        selector.model_name = self.model_name
        self._start_agent()

    # -- Agent lifecycle ------------------------------------------------------

    @work(exclusive=True, thread=False)
    async def _start_agent(self) -> None:
        """Initialize the Copilot agent in a worker."""
        self._agent = PlugboardAgent(
            model=self.model_name,
            on_assistant_delta=self._handle_agent_delta,
            on_assistant_message=self._handle_agent_msg,
            on_tool_start=self._handle_agent_tool,
            on_user_input_request=self._handle_user_input,
            on_mermaid_url=self._handle_mermaid_url,
            on_idle=self._handle_agent_idle,
        )
        try:
            await self._agent.start()
            self.model_name = self._agent.model
            selector = self.query_one(
                "#model-selector",
                ModelSelector,
            )
            selector.model_name = self.model_name
            self.post_message(
                AgentStatus("Connected to GitHub Copilot."),
            )
        except Exception as e:
            self.post_message(
                AgentStatus(
                    f"Failed to connect to Copilot: {e}"
                    "\n\nMake sure the GitHub Copilot CLI "
                    "is installed and you are authenticated.",
                ),
            )

    # -- Agent callbacks ------------------------------------------------------
    # Invoked by the Copilot SDK from within the same async event
    # loop.  We forward them as Textual Messages so that all UI
    # mutations happen through normal message dispatch.

    def _handle_agent_delta(self, delta: str) -> None:
        self.post_message(AgentDelta(delta))

    def _handle_agent_msg(self, content: str) -> None:
        self.post_message(AgentMessage(content))

    def _handle_agent_tool(self, tool_name: str) -> None:
        self.post_message(AgentToolStart(tool_name))

    async def _handle_user_input(
        self,
        request: UserInputRequest,
        invocation: dict[str, str],
    ) -> UserInputResponse:
        """Handle the agent asking the user a question."""
        question = request.get("question", "")
        choices = request.get("choices")

        prompt_text = question
        if choices:
            prompt_text += "\n\nChoices:\n" + "\n".join(f"- {c}" for c in choices)
        self.post_message(AgentQuestion(prompt_text))

        loop = asyncio.get_running_loop()
        self._user_input_future = loop.create_future()
        self._waiting_for_user_input = True

        result = await self._user_input_future
        self._waiting_for_user_input = False
        return result

    def _handle_mermaid_url(self, url: str) -> None:
        self.post_message(AgentMermaidUrl(url))

    def _handle_agent_idle(self) -> None:
        self.post_message(AgentIdle())

    # -- Textual message handlers (run on main thread) ------------------------

    def on_agent_delta(self, message: AgentDelta) -> None:
        """Append streaming chunk to the assistant message."""
        if self._current_assistant_msg is None:
            chat = self.query_one(
                "#chat-scroll",
                VerticalScroll,
            )
            self._current_assistant_msg = ChatMessage(
                "",
                role="assistant",
            )
            chat.mount(self._current_assistant_msg)
        self._current_assistant_msg.append_content(
            message.delta,
        )
        self._current_assistant_msg.scroll_visible()

    def on_agent_message(
        self,
        message: AgentMessage,
    ) -> None:
        """Finalize the current assistant message."""
        if self._current_assistant_msg is not None:
            self._current_assistant_msg.append_content("")
        self._current_assistant_msg = None

    def on_agent_tool_start(
        self,
        message: AgentToolStart,
    ) -> None:
        """Show a system note when a tool starts."""
        self._add_system_message(
            f"Running tool: `{message.tool_name}`...",
        )

    def on_agent_question(
        self,
        message: AgentQuestion,
    ) -> None:
        """Display the agent question and prompt the user."""
        self._add_chat_message(
            message.text,
            role="assistant",
        )
        inp = self.query_one("#chat-input", Input)
        inp.placeholder = "Type your answer..."

    def on_agent_mermaid_url(
        self,
        message: AgentMermaidUrl,
    ) -> None:
        """Update the mermaid diagram link."""
        self.mermaid_url = message.url
        link = self.query_one("#mermaid-link", MermaidLink)
        link.url = message.url

    def on_agent_idle(self, message: AgentIdle) -> None:
        """Reset state when the session goes idle."""
        self._current_assistant_msg = None

    def on_agent_status(
        self,
        message: AgentStatus,
    ) -> None:
        """Display a system status message."""
        self._add_system_message(message.text)

    # -- UI helpers -----------------------------------------------------------

    def _add_system_message(self, text: str) -> None:
        """Add a system message to the chat."""
        self._add_chat_message(text, role="system")

    def _append_to_last_message(self, text: str, role: str) -> bool:
        """Append text to the last message when the role matches."""
        chat = self.query_one("#chat-scroll", VerticalScroll)
        messages = list(chat.query(ChatMessage))
        if not messages or messages[-1].role != role:
            return False
        last_message = messages[-1]
        combined = f"{last_message.content}\n\n{text.rstrip()}".strip()
        last_message.replace_content(combined)
        last_message.scroll_visible()
        return True

    def _add_chat_message(
        self,
        text: str,
        role: str = "assistant",
    ) -> None:
        """Add a message to the chat scroll area."""
        if self._append_to_last_message(text, role):
            return
        chat = self.query_one("#chat-scroll", VerticalScroll)
        msg = ChatMessage(text.rstrip(), role=role)
        chat.mount(msg)
        msg.scroll_visible()

    # -- Input Handling -------------------------------------------------------

    @on(Input.Submitted, "#chat-input")
    def handle_chat_submit(
        self,
        event: Input.Submitted,
    ) -> None:
        """Handle user submitting a chat message."""
        text = event.value.strip()
        if not text:
            return
        event.input.clear()

        if self._waiting_for_user_input and self._user_input_future is not None:
            self._add_chat_message(text, role="user")
            self._user_input_future.set_result(
                UserInputResponse(answer=text, wasFreeform=True),
            )
            inp = self.query_one("#chat-input", Input)
            inp.placeholder = "Describe your model..."
            return

        self._add_chat_message(text, role="user")
        self._send_to_agent(text)

    @work(exclusive=True, thread=False)
    async def _send_to_agent(self, text: str) -> None:
        """Send a message to the agent in a worker."""
        if self._agent is None:
            self._add_system_message(
                "Agent is not connected yet. Please wait...",
            )
            return
        try:
            await self._agent.send(text)
        except Exception as e:
            self._add_system_message(f"Error: {e}")

    # -- Model Selection ------------------------------------------------------

    def action_select_model(self) -> None:
        """Show the model selection overlay."""
        overlay = self.query_one(
            "#model-overlay",
            ModelSelectionOverlay,
        )
        if overlay.has_class("visible"):
            overlay.remove_class("visible")
            return
        overlay.add_class("visible")
        overlay.focus()
        self._fetch_models()

    @work(exclusive=True, thread=False)
    async def _fetch_models(self) -> None:
        """Fetch available models from the agent."""
        fallback = [
            "gpt-4o",
            "gpt-5",
            "claude-sonnet-4",
            "claude-sonnet-4-thinking",
            "o3",
        ]
        if self._agent is None:
            self._populate_model_list(fallback)
            return
        models = await self._agent.list_models()
        if not models:
            models = fallback
        self._populate_model_list(models)

    def _populate_model_list(
        self,
        models: list[str],
    ) -> None:
        """Populate the model selection overlay."""
        overlay = self.query_one(
            "#model-overlay",
            ModelSelectionOverlay,
        )
        overlay.set_models(models, self.model_name)
        option_list = overlay.query_one("#model-list", OptionList)
        option_list.focus()

    @on(OptionList.OptionSelected, "#model-list")
    def handle_model_selected(
        self,
        event: OptionList.OptionSelected,
    ) -> None:
        """Handle model selection."""
        model_id = event.option.id
        if model_id and model_id != self.model_name:
            self.model_name = model_id
            selector = self.query_one(
                "#model-selector",
                ModelSelector,
            )
            selector.model_name = model_id
            self._add_system_message(
                f"Switching to model: **{model_id}**...",
            )
            self._change_model(model_id)

        overlay = self.query_one(
            "#model-overlay",
            ModelSelectionOverlay,
        )
        overlay.remove_class("visible")

    @work(exclusive=True, thread=False)
    async def _change_model(self, model: str) -> None:
        """Change the agent model."""
        if self._agent is not None:
            try:
                await self._agent.change_model(model)
                self._add_system_message(
                    f"Now using model: **{model}**",
                )
                self.query_one("#chat-input", Input).focus()
            except Exception as e:
                self._add_system_message(
                    f"Error changing model: {e}",
                )

    # -- Cleanup --------------------------------------------------------------

    async def action_quit(self) -> None:
        """Clean up and quit."""
        if self._agent is not None:
            await self._agent.stop()
        self.exit()
