# src/friday/approval/telegram.py
import logging
import time
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes, MessageHandler, filters

from friday.approval.queue import ActionQueue
from friday.approval.secure import (
    RateLimitExceeded,
    SecureApprovalManager,
    TotpInvalid,
    TotpRequired,
)

logger = logging.getLogger(__name__)

CALLBACK_PREFIX = "approval:"
PENDING_2FA_TIMEOUT = 300  # 5 minutes


def _get_manager() -> tuple[SecureApprovalManager, ActionQueue]:
    """Create a SecureApprovalManager from config. Returns (manager, queue)."""
    queue = ActionQueue()
    manager = SecureApprovalManager.from_config(queue)
    return manager, queue


async def send_approval_request(
    bot,
    chat_id: int,
    action: dict[str, Any],
    manager: SecureApprovalManager | None = None,
) -> None:
    """Send an approval request to a Telegram chat with inline buttons."""
    action_id = action["id"]

    # Flag high-risk actions that will require 2FA
    risk_tag = ""
    if manager and manager.requires_second_factor(action):
        risk_tag = " [2FA Required]"

    text = (
        f"Approval Required{risk_tag}\n\n"
        f"Action: {action['action_type']}\n"
        f"Description: {action['description']}\n"
        f"Business ID: {action['business_id']}\n"
        f"Level: {action['autonomy_level']}\n"
        f"ID: #{action_id}"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Approve", callback_data=f"{CALLBACK_PREFIX}approve:{action_id}"),
            InlineKeyboardButton("Deny", callback_data=f"{CALLBACK_PREFIX}deny:{action_id}"),
        ]
    ])

    await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)


async def handle_approval_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle inline button presses for approval/denial."""
    query = update.callback_query
    data = query.data

    if not data or not data.startswith(CALLBACK_PREFIX):
        return

    parts = data[len(CALLBACK_PREFIX):].split(":", 1)
    if len(parts) != 2:
        await query.answer("Invalid callback data")
        return

    decision, action_id_str = parts
    try:
        action_id = int(action_id_str)
    except ValueError:
        await query.answer("Invalid action ID")
        return

    manager, queue = _get_manager()
    try:
        if decision == "approve":
            try:
                result = manager.approve(action_id, decided_by="telegram")
                if result:
                    await query.answer(f"Approved action #{action_id}")
                    await query.edit_message_text(
                        f"{query.message.text}\n\n--- Approved via Telegram ---"
                    )
                else:
                    await query.answer(f"Action #{action_id} is no longer pending")
            except TotpRequired:
                # Store pending 2FA state and prompt for code
                context.user_data["pending_2fa"] = {
                    "action_id": action_id,
                    "timestamp": time.time(),
                }
                await query.answer("2FA code required")
                await query.edit_message_text(
                    f"{query.message.text}\n\n"
                    f"Enter your 6-digit authenticator code to approve action #{action_id}:"
                )
            except RateLimitExceeded as e:
                await query.answer(f"Rate limit exceeded: {e}")
                await query.edit_message_text(
                    f"{query.message.text}\n\n--- BLOCKED: Rate limit exceeded ---"
                )
            except TotpInvalid:
                await query.answer("Invalid TOTP code")
        else:
            # Deny — no rate limit or 2FA needed
            result = manager.deny(action_id, decided_by="telegram")
            if result:
                await query.answer(f"Denied action #{action_id}")
                await query.edit_message_text(
                    f"{query.message.text}\n\n--- Denied via Telegram ---"
                )
            else:
                await query.answer(f"Action #{action_id} is no longer pending")
    finally:
        queue.close()


async def handle_2fa_code(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle 6-digit TOTP code messages for pending 2FA approvals."""
    pending = context.user_data.get("pending_2fa")
    if not pending:
        return

    # Check expiry
    if time.time() - pending["timestamp"] > PENDING_2FA_TIMEOUT:
        context.user_data.pop("pending_2fa", None)
        await update.message.reply_text(
            "2FA verification expired. Please approve the action again."
        )
        return

    code = update.message.text.strip()
    action_id = pending["action_id"]

    manager, queue = _get_manager()
    try:
        try:
            result = manager.approve(
                action_id, decided_by="telegram", totp_code=code
            )
            context.user_data.pop("pending_2fa", None)
            if result:
                await update.message.reply_text(
                    f"Action #{action_id} approved with 2FA verification."
                )
            else:
                await update.message.reply_text(
                    f"Action #{action_id} is no longer pending."
                )
        except TotpInvalid:
            await update.message.reply_text(
                "Invalid authenticator code. Please try again."
            )
        except RateLimitExceeded as e:
            context.user_data.pop("pending_2fa", None)
            await update.message.reply_text(f"Approval blocked: {e}")
    finally:
        queue.close()


def get_approval_handler() -> CallbackQueryHandler:
    """Return a CallbackQueryHandler to register on the Telegram Application."""
    return CallbackQueryHandler(
        handle_approval_callback,
        pattern=f"^{CALLBACK_PREFIX}",
    )


def get_2fa_handler() -> MessageHandler:
    """Return a MessageHandler for 6-digit TOTP codes."""
    return MessageHandler(
        filters.Regex(r"^\d{6}$") & ~filters.COMMAND,
        handle_2fa_code,
    )
