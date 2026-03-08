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
        bot._action_queue_factory = lambda: mock_queue

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
        bot._action_queue_factory = lambda: mock_queue

        await bot.cmd_pending(update, MagicMock())

        msg = update.message.reply_text.call_args[0][0]
        assert "2 pending" in msg
        assert "email_send" in msg
        assert "stripe_charge" in msg

    # --- handle_message happy path + error ---

    @pytest.mark.asyncio
    async def test_handle_message_uses_pool(self):
        """handle_message should route through pool.submit, not blocking agent.run."""
        bot = MerkabaBot(token="test", allowed_user_ids=[111])

        # Track calls manually to avoid AsyncMock event-loop issues in full suite
        submit_calls = []

        async def mock_submit(session_id, message):
            submit_calls.append((session_id, message))
            return "Hello! I'm Merkaba."

        mock_pool = MagicMock()
        mock_pool.submit = mock_submit
        bot.pool = mock_pool

        reply_calls = []

        async def mock_reply(text):
            reply_calls.append(text)

        update = MagicMock()
        update.effective_user.id = 111
        update.message.text = "Hi there"
        update.message.message_thread_id = None
        update.message.reply_text = mock_reply

        await bot.handle_message(update, MagicMock())

        assert len(submit_calls) == 1
        assert submit_calls[0][0] == "telegram:111"  # session_id
        assert submit_calls[0][1] == "Hi there"  # message
        assert len(reply_calls) == 1
        assert reply_calls[0] == "Hello! I'm Merkaba."

    @pytest.mark.asyncio
    async def test_handle_message_includes_topic_id(self):
        """Session ID includes topic_id for Telegram threads."""
        bot = MerkabaBot(token="test", allowed_user_ids=[456])
        bot.pool = MagicMock()
        bot.pool.submit = AsyncMock(return_value="response")

        update = MagicMock()
        update.effective_user.id = 456
        update.message.text = "hello"
        update.message.message_thread_id = 789
        update.message.reply_text = AsyncMock()

        await bot.handle_message(update, MagicMock())

        call_args = bot.pool.submit.call_args
        session_id = call_args[0][0]
        assert session_id == "telegram:456:topic:789"

    @pytest.mark.asyncio
    async def test_handle_message_pool_error(self):
        """handle_message should send error message when pool.submit raises."""
        bot = MerkabaBot(token="test", allowed_user_ids=[111])
        bot.pool = MagicMock()
        bot.pool.submit = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

        update = MagicMock()
        update.effective_user.id = 111
        update.message.text = "Hello"
        update.message.message_thread_id = None
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

    # --- SessionPool skill activation path ---

    def test_pool_skill_activation_api_exists(self):
        """Skill activation should go through the SessionPool API."""
        bot = MerkabaBot(token="test", allowed_user_ids=[111])
        assert hasattr(bot.pool, "set_active_skill")

    def test_pool_initialized_on_creation(self):
        """SessionPool should be initialized in __post_init__."""
        bot = MerkabaBot(token="test", allowed_user_ids=[111])
        from merkaba.orchestration.session_pool import SessionPool
        assert isinstance(bot.pool, SessionPool)


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
        mock_update.message.message_thread_id = None
        mock_update.message.reply_text = AsyncMock()

        mock_context = MagicMock()
        mock_context.args = []

        bot.pool = MagicMock()

        await bot.handle_skill_command(mock_update, mock_context, "brainstorming")

        bot.pool.set_active_skill.assert_called_once_with("telegram:111", mock_skill)

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
