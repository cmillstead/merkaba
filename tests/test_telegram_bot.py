# tests/test_telegram_bot.py
"""Tests for Telegram bot handler."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Check if required dependencies are available
try:
    from merkaba.telegram.bot import MerkabaBot
    HAS_DEPENDENCIES = True
except ImportError as e:
    HAS_DEPENDENCIES = False
    IMPORT_ERROR = str(e)
    MerkabaBot = None

pytestmark = pytest.mark.skipif(
    not HAS_DEPENDENCIES,
    reason=f"Missing required dependencies: {IMPORT_ERROR if not HAS_DEPENDENCIES else ''}"
)


class TestMerkabaBot:
    """Tests for MerkabaBot class."""

    def test_bot_initializes_with_token(self):
        """MerkabaBot should initialize with a token."""
        bot = MerkabaBot(token="test_token", allowed_user_ids=[123])
        assert bot.token == "test_token"
        assert bot.allowed_user_ids == [123]

    def test_is_authorized_checks_user_id(self):
        """is_authorized should check if user is in allowed list."""
        bot = MerkabaBot(token="test", allowed_user_ids=[111, 222])
        assert bot.is_authorized(111) is True
        assert bot.is_authorized(999) is False

    @pytest.mark.asyncio
    async def test_handle_message_rejects_unauthorized(self):
        """handle_message should reject unauthorized users."""
        bot = MerkabaBot(token="test", allowed_user_ids=[111])

        mock_update = MagicMock()
        mock_update.effective_user.id = 999
        mock_update.message.reply_text = AsyncMock()

        mock_context = MagicMock()

        await bot.handle_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "not authorized" in call_args.lower()


    # --- cmd_start ---

    @pytest.mark.asyncio
    async def test_cmd_start_authorized(self):
        """cmd_start should send welcome message for authorized users."""
        bot = MerkabaBot(token="test", allowed_user_ids=[111])
        update = MagicMock()
        update.effective_user.id = 111
        update.message.reply_text = AsyncMock()

        await bot.cmd_start(update, MagicMock())

        update.message.reply_text.assert_called_once()
        msg = update.message.reply_text.call_args[0][0]
        assert "Merkaba is online" in msg

    @pytest.mark.asyncio
    async def test_cmd_start_unauthorized(self):
        """cmd_start should reject unauthorized users."""
        bot = MerkabaBot(token="test", allowed_user_ids=[111])
        update = MagicMock()
        update.effective_user.id = 999
        update.message.reply_text = AsyncMock()

        await bot.cmd_start(update, MagicMock())

        msg = update.message.reply_text.call_args[0][0]
        assert "not authorized" in msg.lower()

    # --- cmd_help ---

    @pytest.mark.asyncio
    async def test_cmd_help_authorized(self):
        """cmd_help should list available commands."""
        bot = MerkabaBot(token="test", allowed_user_ids=[111])
        update = MagicMock()
        update.effective_user.id = 111
        update.message.reply_text = AsyncMock()

        await bot.cmd_help(update, MagicMock())

        msg = update.message.reply_text.call_args[0][0]
        assert "Available Commands" in msg
        assert "/start" in msg
        assert "/help" in msg
        assert "/research" in msg

    @pytest.mark.asyncio
    async def test_cmd_help_unauthorized(self):
        """cmd_help should reject unauthorized users."""
        bot = MerkabaBot(token="test", allowed_user_ids=[111])
        update = MagicMock()
        update.effective_user.id = 999
        update.message.reply_text = AsyncMock()

        await bot.cmd_help(update, MagicMock())

        msg = update.message.reply_text.call_args[0][0]
        assert "not authorized" in msg.lower()

    # --- cmd_status ---

    @pytest.mark.asyncio
    async def test_cmd_status_authorized(self):
        """cmd_status should report running status."""
        bot = MerkabaBot(token="test", allowed_user_ids=[111])
        update = MagicMock()
        update.effective_user.id = 111
        update.message.reply_text = AsyncMock()

        await bot.cmd_status(update, MagicMock())

        msg = update.message.reply_text.call_args[0][0]
        assert "running" in msg.lower()

    @pytest.mark.asyncio
    async def test_cmd_status_unauthorized(self):
        """cmd_status should reject unauthorized users."""
        bot = MerkabaBot(token="test", allowed_user_ids=[111])
        update = MagicMock()
        update.effective_user.id = 999
        update.message.reply_text = AsyncMock()

        await bot.cmd_status(update, MagicMock())

        msg = update.message.reply_text.call_args[0][0]
        assert "not authorized" in msg.lower()

    # --- cmd_pending ---

    @pytest.mark.asyncio
    async def test_cmd_pending_unauthorized(self):
        """cmd_pending should reject unauthorized users."""
        bot = MerkabaBot(token="test", allowed_user_ids=[111])
        update = MagicMock()
        update.effective_user.id = 999
        update.message.reply_text = AsyncMock()

        await bot.cmd_pending(update, MagicMock())

        msg = update.message.reply_text.call_args[0][0]
        assert "not authorized" in msg.lower()

    @pytest.mark.asyncio
    async def test_cmd_pending_no_actions(self):
        """cmd_pending should report no pending approvals when queue is empty."""
        bot = MerkabaBot(token="test", allowed_user_ids=[111])
        update = MagicMock()
        update.effective_user.id = 111
        update.message.reply_text = AsyncMock()

        mock_queue = MagicMock()
        mock_queue.list_actions.return_value = []

        with patch("merkaba.approval.queue.ActionQueue", return_value=mock_queue):
            await bot.cmd_pending(update, MagicMock())

        msg = update.message.reply_text.call_args[0][0]
        assert "no pending" in msg.lower()

    @pytest.mark.asyncio
    async def test_cmd_pending_with_actions(self):
        """cmd_pending should list pending approvals."""
        bot = MerkabaBot(token="test", allowed_user_ids=[111])
        update = MagicMock()
        update.effective_user.id = 111
        update.message.reply_text = AsyncMock()

        mock_queue = MagicMock()
        mock_queue.list_actions.return_value = [
            {"id": 1, "action_type": "email_send", "description": "Send welcome email"},
            {"id": 2, "action_type": "stripe_charge", "description": "Charge customer $50"},
        ]

        with patch("merkaba.approval.queue.ActionQueue", return_value=mock_queue):
            await bot.cmd_pending(update, MagicMock())

        msg = update.message.reply_text.call_args[0][0]
        assert "2 pending" in msg
        assert "email_send" in msg
        assert "stripe_charge" in msg

    # --- handle_message happy path + error ---

    @pytest.mark.asyncio
    async def test_handle_message_happy_path(self):
        """handle_message should pass message to agent and return response."""
        bot = MerkabaBot(token="test", allowed_user_ids=[111])
        bot.agent = MagicMock()
        bot.agent.run.return_value = "Hello! I'm Merkaba."

        update = MagicMock()
        update.effective_user.id = 111
        update.message.text = "Hi there"
        update.message.reply_text = AsyncMock()

        await bot.handle_message(update, MagicMock())

        bot.agent.run.assert_called_once_with("Hi there")
        msg = update.message.reply_text.call_args[0][0]
        assert "Hello! I'm Merkaba." == msg

    @pytest.mark.asyncio
    async def test_handle_message_agent_error(self):
        """handle_message should send error message when agent raises."""
        bot = MerkabaBot(token="test", allowed_user_ids=[111])
        bot.agent = MagicMock()
        bot.agent.run.side_effect = RuntimeError("LLM unavailable")

        update = MagicMock()
        update.effective_user.id = 111
        update.message.text = "Hello"
        update.message.reply_text = AsyncMock()

        await bot.handle_message(update, MagicMock())

        msg = update.message.reply_text.call_args[0][0]
        assert "something went wrong" in msg.lower()

    # --- _wrap_auth ---

    @pytest.mark.asyncio
    async def test_wrap_auth_allows_authorized(self):
        """_wrap_auth should call wrapped handler for authorized users."""
        bot = MerkabaBot(token="test", allowed_user_ids=[111])
        inner = AsyncMock()
        wrapped = bot._wrap_auth(inner)

        update = MagicMock()
        update.effective_user.id = 111
        context = MagicMock()

        await wrapped(update, context)
        inner.assert_called_once_with(update, context)

    @pytest.mark.asyncio
    async def test_wrap_auth_blocks_unauthorized(self):
        """_wrap_auth should block unauthorized users."""
        bot = MerkabaBot(token="test", allowed_user_ids=[111])
        inner = AsyncMock()
        wrapped = bot._wrap_auth(inner)

        update = MagicMock()
        update.effective_user.id = 999
        update.message.reply_text = AsyncMock()
        context = MagicMock()

        await wrapped(update, context)
        inner.assert_not_called()
        msg = update.message.reply_text.call_args[0][0]
        assert "not authorized" in msg.lower()

    # --- _get_agent lazy init ---

    def test_get_agent_lazy_init(self):
        """_get_agent should create agent on first call and reuse it."""
        bot = MerkabaBot(token="test", allowed_user_ids=[111])
        assert bot.agent is None

        with patch("merkaba.telegram.bot.Agent") as MockAgent:
            agent1 = bot._get_agent()
            agent2 = bot._get_agent()

        assert agent1 is agent2
        MockAgent.assert_called_once()


class TestBotSkillInvocation:
    """Tests for skill invocation via Telegram."""

    @pytest.mark.asyncio
    async def test_slash_skill_invokes_skill(self):
        """Bot should invoke skill when user types /skill-name."""
        from merkaba.plugins import Skill

        bot = MerkabaBot(token="test", allowed_user_ids=[111])

        mock_skill = Skill(
            name="brainstorming",
            description="Creative design",
            content="Be creative",
        )
        bot.plugin_registry = MagicMock()
        bot.plugin_registry.skills.get.return_value = mock_skill

        mock_update = MagicMock()
        mock_update.effective_user.id = 111
        mock_update.message.text = "/brainstorming"
        mock_update.message.reply_text = AsyncMock()

        mock_context = MagicMock()
        mock_context.args = []

        await bot.handle_skill_command(mock_update, mock_context, "brainstorming")

        # Verify skill was activated
        assert bot.agent.active_skill == mock_skill

    @pytest.mark.asyncio
    async def test_skill_not_found(self):
        """handle_skill_command should report when skill not found."""
        bot = MerkabaBot(token="test", allowed_user_ids=[111])
        bot.plugin_registry = MagicMock()
        bot.plugin_registry.skills.get.return_value = None

        update = MagicMock()
        update.effective_user.id = 111
        update.message.reply_text = AsyncMock()

        await bot.handle_skill_command(update, MagicMock(), "nonexistent")

        msg = update.message.reply_text.call_args[0][0]
        assert "not found" in msg.lower()

    @pytest.mark.asyncio
    async def test_skill_command_unauthorized(self):
        """handle_skill_command should reject unauthorized users."""
        bot = MerkabaBot(token="test", allowed_user_ids=[111])

        update = MagicMock()
        update.effective_user.id = 999
        update.message.reply_text = AsyncMock()

        await bot.handle_skill_command(update, MagicMock(), "brainstorming")

        msg = update.message.reply_text.call_args[0][0]
        assert "not authorized" in msg.lower()
