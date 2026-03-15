"""Unit tests for the Plugboard Go CLI module."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from plugboard.cli import app


runner = CliRunner()


# ---------------------------------------------------------------------------
# CLI entry-point / dependency-check tests
# ---------------------------------------------------------------------------


class TestGoCliEntrypoint:
    """Tests for the ``plugboard go`` CLI sub-command entry-point."""

    def test_go_missing_copilot_dependency(self) -> None:
        """Should exit with an error when the 'copilot' package is missing."""
        with patch(
            "plugboard.utils.dependencies.find_spec",
            side_effect=lambda name: object() if name == "textual" else None,
        ):
            result = runner.invoke(app, ["go"])
            assert result.exit_code == 1
            assert "Optional dependency copilot not found" in result.stdout
            assert "pip install plugboard[go]" in result.stdout

    def test_go_missing_textual_dependency(self) -> None:
        """Should exit with an error when the 'textual' package is missing."""
        with patch(
            "plugboard.utils.dependencies.find_spec",
            side_effect=lambda name: None if name == "textual" else object(),
        ):
            result = runner.invoke(app, ["go"])
            assert result.exit_code == 1
            assert "Optional dependency textual not found" in result.stdout

    def test_go_default_model_option(self) -> None:
        """The --model flag should default to gpt-4o."""
        with patch("plugboard.cli.go.app.PlugboardGoApp") as mock_app_cls:
            mock_app = MagicMock()
            mock_app_cls.return_value = mock_app
            result = runner.invoke(app, ["go"])
            assert result.exit_code == 0
            mock_app_cls.assert_called_once_with(model_name="gpt-4o")
            mock_app.run.assert_called_once()

    def test_go_custom_model_option(self) -> None:
        """The --model flag should accept a custom model name."""
        with patch("plugboard.cli.go.app.PlugboardGoApp") as mock_app_cls:
            mock_app = MagicMock()
            mock_app_cls.return_value = mock_app
            result = runner.invoke(app, ["go", "--model", "claude-sonnet-4"])
            assert result.exit_code == 0
            mock_app_cls.assert_called_once_with(model_name="claude-sonnet-4")

    def test_go_short_model_flag(self) -> None:
        """The -m short flag should work."""
        with patch("plugboard.cli.go.app.PlugboardGoApp") as mock_app_cls:
            mock_app = MagicMock()
            mock_app_cls.return_value = mock_app
            result = runner.invoke(app, ["go", "-m", "gpt-5"])
            assert result.exit_code == 0
            mock_app_cls.assert_called_once_with(model_name="gpt-5")


# ---------------------------------------------------------------------------
# System prompt loading tests
# ---------------------------------------------------------------------------


class TestLoadSystemPrompt:
    """Tests for ``_load_system_prompt``."""

    def test_loads_from_package_data(self) -> None:
        """Should load AGENTS.md from importlib.resources (package data)."""
        from plugboard.cli.go.agent import _load_system_prompt

        prompt = _load_system_prompt()
        # The bundled AGENTS.md starts with this heading
        assert "Plugboard" in prompt
        assert len(prompt) > 100

    def test_falls_back_to_cwd(self, tmp_path: Path) -> None:
        """Should fall back to examples/AGENTS.md in cwd when package data unavailable."""
        from plugboard.cli.go.agent import _load_system_prompt

        # Create fake AGENTS.md in tmp_path
        examples_dir = tmp_path / "examples"
        examples_dir.mkdir()
        agents_file = examples_dir / "AGENTS.md"
        agents_file.write_text("# Test prompt from cwd")

        with (
            patch(
                "plugboard.cli.go.agent.resources.files",
                side_effect=FileNotFoundError,
            ),
            patch("plugboard.cli.go.agent.Path.cwd", return_value=tmp_path),
        ):
            prompt = _load_system_prompt()

        assert prompt == "# Test prompt from cwd"

    def test_falls_back_to_builtin(self) -> None:
        """Should use the built-in fallback when neither source is available."""
        from plugboard.cli.go.agent import (
            _FALLBACK_SYSTEM_PROMPT,
            _load_system_prompt,
        )

        with (
            patch(
                "plugboard.cli.go.agent.resources.files",
                side_effect=FileNotFoundError,
            ),
            patch(
                "plugboard.cli.go.agent.Path.cwd",
                return_value=Path("/nonexistent"),
            ),
        ):
            prompt = _load_system_prompt()

        assert prompt == _FALLBACK_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# PlugboardAgent tests
# ---------------------------------------------------------------------------


class TestPlugboardAgent:
    """Tests for PlugboardAgent initialization and callbacks."""

    def test_agent_init(self) -> None:
        """Agent should store model and callbacks."""
        from plugboard.cli.go.agent import PlugboardAgent

        delta_cb = MagicMock()
        msg_cb = MagicMock()

        agent = PlugboardAgent(
            model="gpt-4o",
            on_assistant_delta=delta_cb,
            on_assistant_message=msg_cb,
        )
        assert agent.model == "gpt-4o"
        assert agent._on_assistant_delta is delta_cb
        assert agent._on_assistant_message is msg_cb

    def test_agent_model_property(self) -> None:
        """The model property should return the configured model."""
        from plugboard.cli.go.agent import PlugboardAgent

        agent = PlugboardAgent(model="gpt-5")
        assert agent.model == "gpt-5"

    @pytest.mark.asyncio
    async def test_send_raises_without_start(self) -> None:
        """send() should raise RuntimeError if agent not started."""
        from plugboard.cli.go.agent import PlugboardAgent

        agent = PlugboardAgent(model="gpt-4o")
        with pytest.raises(RuntimeError, match="not started"):
            await agent.send("hello")

    @pytest.mark.asyncio
    async def test_list_models_raises_without_start(self) -> None:
        """list_models() should raise RuntimeError if agent not started."""
        from plugboard.cli.go.agent import PlugboardAgent

        agent = PlugboardAgent(model="gpt-4o")
        with pytest.raises(RuntimeError, match="not started"):
            await agent.list_models()

    @pytest.mark.asyncio
    async def test_stop_is_safe_without_start(self) -> None:
        """stop() should not raise even if agent was never started."""
        from plugboard.cli.go.agent import PlugboardAgent

        agent = PlugboardAgent(model="gpt-4o")
        # Should not raise
        await agent.stop()
        assert agent._client is None
        assert agent._session is None

    @pytest.mark.asyncio
    async def test_change_model_restarts_agent(self) -> None:
        """change_model() should restart the agent cleanly."""
        from plugboard.cli.go.agent import PlugboardAgent

        agent = PlugboardAgent(model="gpt-4o")

        with (
            patch.object(agent, "stop", new=AsyncMock()) as mock_stop,
            patch.object(agent, "start", new=AsyncMock()) as mock_start,
        ):
            await agent.change_model("gpt-5")

        assert agent.model == "gpt-5"
        mock_stop.assert_awaited_once()
        mock_start.assert_awaited_once()


# ---------------------------------------------------------------------------
# App widget / message tests
# ---------------------------------------------------------------------------


class TestAppWidgets:
    """Tests for Plugboard Go TUI widgets and messages."""

    def test_chat_message_roles(self) -> None:
        """ChatMessage should accept user/assistant/system roles."""
        from plugboard.cli.go.app import ChatMessage

        for role in ("user", "assistant", "system"):
            msg = ChatMessage("test content", role=role)
            assert role in msg.classes

    def test_agent_delta_message(self) -> None:
        """AgentDelta message should store delta text."""
        from plugboard.cli.go.app import AgentDelta

        msg = AgentDelta("hello")
        assert msg.delta == "hello"

    def test_agent_message(self) -> None:
        """AgentMessage should store content."""
        from plugboard.cli.go.app import AgentMessage

        msg = AgentMessage("full response")
        assert msg.content == "full response"

    def test_agent_tool_start_message(self) -> None:
        """AgentToolStart should store tool name."""
        from plugboard.cli.go.app import AgentToolStart

        msg = AgentToolStart("run_plugboard_model")
        assert msg.tool_name == "run_plugboard_model"

    def test_agent_question_message(self) -> None:
        """AgentQuestion should store text."""
        from plugboard.cli.go.app import AgentQuestion

        msg = AgentQuestion("What model?")
        assert msg.text == "What model?"

    def test_agent_mermaid_url_message(self) -> None:
        """AgentMermaidUrl should store URL."""
        from plugboard.cli.go.app import AgentMermaidUrl

        msg = AgentMermaidUrl("https://example.com")
        assert msg.url == "https://example.com"

    def test_agent_idle_message(self) -> None:
        """AgentIdle should be constructable."""
        from plugboard.cli.go.app import AgentIdle

        msg = AgentIdle()
        assert isinstance(msg, AgentIdle)

    def test_agent_status_message(self) -> None:
        """AgentStatus should store text."""
        from plugboard.cli.go.app import AgentStatus

        msg = AgentStatus("Connected")
        assert msg.text == "Connected"

    def test_model_selector_default(self) -> None:
        """ModelSelector default model should be gpt-4o."""
        from plugboard.cli.go.app import ModelSelector

        selector = ModelSelector()
        assert selector.model_name == "gpt-4o"

    def test_mermaid_link_default(self) -> None:
        """MermaidLink default URL should be empty."""
        from plugboard.cli.go.app import MermaidLink

        link = MermaidLink()
        assert link.url == ""


# ---------------------------------------------------------------------------
# Tool parameter model tests
# ---------------------------------------------------------------------------


class TestToolParams:
    """Tests for Copilot tool parameter models."""

    def test_run_model_params(self) -> None:
        """RunModelParams should validate yaml_path."""
        from plugboard.cli.go.tools import RunModelParams

        params = RunModelParams(yaml_path="/path/to/model.yaml")
        assert params.yaml_path == "/path/to/model.yaml"

    def test_mermaid_diagram_params(self) -> None:
        """MermaidDiagramParams should validate yaml_path."""
        from plugboard.cli.go.tools import MermaidDiagramParams

        params = MermaidDiagramParams(yaml_path="config.yml")
        assert params.yaml_path == "config.yml"


# ---------------------------------------------------------------------------
# App construction test (Textual pilot)
# ---------------------------------------------------------------------------


class TestPlugboardGoApp:
    """Tests for the main PlugboardGoApp."""

    def test_app_construction(self) -> None:
        """App should initialize with default and custom model names."""
        from plugboard.cli.go.app import PlugboardGoApp

        app = PlugboardGoApp()
        assert app.model_name == "gpt-4o"

        app2 = PlugboardGoApp(model_name="claude-sonnet-4")
        assert app2.model_name == "claude-sonnet-4"

    def test_app_uses_shared_theme_colors(self) -> None:
        """App CSS should use the shared theme constants."""
        from plugboard.cli.go.app import PlugboardGoApp
        from plugboard.utils.theme import PlugboardTheme

        app = PlugboardGoApp()
        assert PlugboardTheme.PB_BLUE in app.CSS
        assert PlugboardTheme.PB_WHITE in app.CSS
        assert PlugboardTheme.PB_ACCENT1 in app.CSS

    def test_app_has_bindings(self) -> None:
        """App should have model-select and quit bindings."""
        from plugboard.cli.go.app import PlugboardGoApp

        app = PlugboardGoApp()
        binding_keys = [b.key for b in app.BINDINGS]
        assert "m" in binding_keys
        assert "q" in binding_keys

    @pytest.mark.asyncio
    async def test_app_compose_mounts(self) -> None:
        """App should compose without errors using Textual test pilot."""
        from plugboard.cli.go.app import PlugboardGoApp

        # Patch the agent start so it doesn't actually connect
        with patch(
            "plugboard.cli.go.app.PlugboardAgent",
        ) as mock_agent_cls:
            mock_agent = AsyncMock()
            mock_agent_cls.return_value = mock_agent

            app = PlugboardGoApp(model_name="gpt-4o")
            async with app.run_test(size=(120, 40)):
                # Main widgets should be mounted
                assert app.query_one("#chat-scroll") is not None
                assert app.query_one("#chat-input") is not None
                assert app.query_one("#model-selector") is not None
                assert app.query_one("#mermaid-link") is not None
                assert app.query_one("#file-tree") is not None
                assert app.query_one("#model-overlay") is not None
                assert app.query_one("#shortcut-hint") is not None
                assert app.query_one("#title-banner") is not None

    @pytest.mark.asyncio
    async def test_app_handles_agent_status_message(self) -> None:
        """AgentStatus messages should appear as system messages."""
        from plugboard.cli.go.app import AgentStatus, PlugboardGoApp

        with patch(
            "plugboard.cli.go.app.PlugboardAgent",
        ) as mock_agent_cls:
            mock_agent = AsyncMock()
            mock_agent_cls.return_value = mock_agent

            app = PlugboardGoApp(model_name="gpt-4o")
            async with app.run_test(size=(120, 40)) as pilot:  # noqa: F841
                app.post_message(AgentStatus("Test status"))
                await asyncio.sleep(0.1)
                # The status message should be merged into the existing
                # welcome system message rather than creating a new card.
                chat_scroll = app.query_one("#chat-scroll")
                from plugboard.cli.go.app import ChatMessage

                messages = chat_scroll.query(ChatMessage)
                assert len(messages) == 1
                assert "Test status" in messages.first()._content

    @pytest.mark.asyncio
    async def test_app_collapses_consecutive_user_messages(self) -> None:
        """Consecutive messages with the same role should collapse."""
        from plugboard.cli.go.app import ChatMessage, PlugboardGoApp

        with patch(
            "plugboard.cli.go.app.PlugboardAgent",
        ) as mock_agent_cls:
            mock_agent = AsyncMock()
            mock_agent_cls.return_value = mock_agent

            app = PlugboardGoApp(model_name="gpt-4o")
            async with app.run_test(size=(120, 40)):
                app._add_chat_message("First user line", role="user")
                app._add_chat_message("Second user line", role="user")

                chat_scroll = app.query_one("#chat-scroll")
                messages = list(chat_scroll.query(ChatMessage))

                assert messages[-1].role == "user"
                assert "First user line\nSecond user line" in messages[-1]._content
