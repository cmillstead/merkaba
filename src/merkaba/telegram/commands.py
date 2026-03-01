# src/merkaba/telegram/commands.py
"""Telegram command handlers for Merkaba."""

import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /cancel command."""
    # TODO: Implement task cancellation
    await update.message.reply_text("No active tasks to cancel")
