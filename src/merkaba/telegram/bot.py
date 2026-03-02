# src/merkaba/telegram/bot.py
"""Telegram bot handler for Merkaba."""

import logging
from dataclasses import dataclass, field

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from merkaba.orchestration.session_pool import SessionPool
from merkaba.orchestration.session import build_session_id
from merkaba.plugins import PluginRegistry
from merkaba.telegram.commands import handle_cancel

logger = logging.getLogger(__name__)


@dataclass
class MerkabaBot:
    """Telegram bot that interfaces with Merkaba agent."""

    token: str
    allowed_user_ids: list[int]
    pool: SessionPool = field(init=False, default=None)
    app: Application = field(init=False, default=None)
    plugin_registry: PluginRegistry = field(init=False, default=None)

    def __post_init__(self):
        self.pool = SessionPool()
        self.plugin_registry = PluginRegistry.default()

    def _get_agent(self):
        """Get or create a default agent for non-pooled operations.

        Used only for skill activation which sets agent state directly.
        Normal message handling goes through self.pool.submit().
        TODO: Rework skill activation to integrate with SessionPool.
        """
        from merkaba.agent import Agent
        if not hasattr(self, "_fallback_agent") or self._fallback_agent is None:
            self._fallback_agent = Agent()
        return self._fallback_agent

    def is_authorized(self, user_id: int) -> bool:
        """Check if user is authorized."""
        return user_id in self.allowed_user_ids

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming text messages.

        Routes through SessionPool.submit() which runs agent.run() in a
        thread via asyncio.to_thread(), preventing event loop blocking.
        """
        user_id = update.effective_user.id

        if not self.is_authorized(user_id):
            await update.message.reply_text("You are not authorized to use this bot.")
            return

        user_message = update.message.text
        logger.info(f"Message from {user_id}: {user_message}")

        # Build session ID with topic awareness (prevents context bleeding)
        topic_id = str(update.message.message_thread_id) if update.message.message_thread_id else None
        session_id = build_session_id("telegram", str(user_id), topic_id=topic_id)

        try:
            # Non-blocking: pool.submit() runs agent.run() in a thread
            response = await self.pool.submit(session_id, user_message)
            await update.message.reply_text(response)
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await update.message.reply_text("Sorry, something went wrong processing your message.")

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        user_id = update.effective_user.id

        if not self.is_authorized(user_id):
            await update.message.reply_text("You are not authorized to use this bot.")
            return

        await update.message.reply_text(
            "Merkaba is online!\n\n"
            "I can help you with:\n"
            "* /research <query> - Search Etsy marketplace\n"
            "* /generate <prompt> - Generate images\n"
            "* /listing - Manage Etsy listings\n"
            "* /status - Check running tasks\n"
            "* /help - Show all commands\n\n"
            "Or just chat naturally!"
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        if not self.is_authorized(update.effective_user.id):
            await update.message.reply_text("You are not authorized to use this bot.")
            return

        await update.message.reply_text(
            "Available Commands:\n\n"
            "/start - Welcome message\n"
            "/help - This help message\n"
            "/status - Show running tasks\n"
            "/research <query> - Start Etsy research\n"
            "/generate <prompt> - Generate images\n"
            "/listing auth - Authenticate with Etsy\n"
            "/listing create - Create draft listing\n"
            "/listing list - Show shop listings\n"
            "/cancel - Cancel running task"
        )

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        if not self.is_authorized(update.effective_user.id):
            await update.message.reply_text("You are not authorized to use this bot.")
            return

        # TODO: Implement task status tracking
        await update.message.reply_text("Merkaba is running\nNo active tasks")

    async def handle_skill_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, skill_name: str
    ):
        """Handle skill invocation via /skill-name."""
        if not self.is_authorized(update.effective_user.id):
            await update.message.reply_text("You are not authorized.")
            return

        skill = self.plugin_registry.skills.get(skill_name)
        if not skill:
            await update.message.reply_text(f"Skill '{skill_name}' not found.")
            return

        # Set the skill directly on the agent
        self._get_agent().active_skill = skill
        await update.message.reply_text(
            f"Activated skill: {skill_name}\n"
            f"{skill.description}\n\n"
            "What would you like to work on?"
        )

    def _wrap_auth(self, handler):
        """Wrap handler with authorization check."""
        async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not self.is_authorized(update.effective_user.id):
                await update.message.reply_text("You are not authorized to use this bot.")
                return
            await handler(update, context)
        return wrapped

    async def cmd_pending(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pending command - show pending approvals."""
        if not self.is_authorized(update.effective_user.id):
            await update.message.reply_text("You are not authorized to use this bot.")
            return

        from merkaba.approval.queue import ActionQueue
        queue = ActionQueue()
        try:
            actions = queue.list_actions(status="pending")
        finally:
            queue.close()

        if not actions:
            await update.message.reply_text("No pending approvals.")
            return

        text = f"{len(actions)} pending approval(s):\n\n"
        for a in actions[:10]:
            text += f"#{a['id']} [{a['action_type']}] {a.get('description', '')[:40]}\n"
        await update.message.reply_text(text)

    def build_app(self) -> Application:
        """Build the Telegram application."""
        self.app = Application.builder().token(self.token).build()

        # Add handlers
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("pending", self.cmd_pending))
        self.app.add_handler(CommandHandler("cancel", self._wrap_auth(handle_cancel)))

        # Add handlers for all loaded skills (skip invalid bot command names)
        import re
        for skill_name in self.plugin_registry.skills.list_skills():
            cmd = skill_name.replace("-", "_")
            if not re.match(r"^[\da-z_]{1,32}$", cmd):
                logger.debug(f"Skipping skill '{skill_name}': invalid bot command name")
                continue
            self.app.add_handler(
                CommandHandler(
                    cmd,
                    lambda u, c, sn=skill_name: self.handle_skill_command(u, c, sn)
                )
            )

        # Add approval inline button handler + 2FA handler (before general text handler)
        try:
            from merkaba.approval.telegram import get_approval_handler, get_2fa_handler
            self.app.add_handler(get_approval_handler())
            self.app.add_handler(get_2fa_handler())
        except ImportError:
            logger.debug("Approval module not available")

        # General text handler (must be after 2FA handler so 6-digit codes route correctly)
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )

        return self.app

    def run(self):
        """Run the bot (blocking). Manages its own event loop."""
        app = self.build_app()
        logger.info("Starting Merkaba Telegram bot...")
        app.run_polling()
