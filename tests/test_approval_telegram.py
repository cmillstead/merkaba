# tests/test_approval_telegram.py
import tempfile
import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    from telegram import InlineKeyboardMarkup
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False

pytestmark = pytest.mark.skipif(not HAS_TELEGRAM, reason="python-telegram-bot not installed")


@pytest.fixture
def queue():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "actions.db")
        from merkaba.approval.queue import ActionQueue
        q = ActionQueue(db_path=db_path)
        yield q
        q.close()


@pytest.fixture
def action(queue):
    aid = queue.add_action(business_id=1, action_type="send_email", description="Send invoice")
    return queue.get_action(aid)


@pytest.fixture
def manager_no_totp(queue):
    from merkaba.approval.secure import SecureApprovalManager, RateLimitConfig
    return SecureApprovalManager(
        action_queue=queue,
        totp_secret=None,
        rate_limit=RateLimitConfig(max_approvals=100, window_seconds=60),
    )


@pytest.fixture
def manager_with_totp(queue):
    import pyotp
    secret = pyotp.random_base32()
    from merkaba.approval.secure import SecureApprovalManager, RateLimitConfig
    return SecureApprovalManager(
        action_queue=queue,
        totp_secret=secret,
        totp_threshold=3,
        rate_limit=RateLimitConfig(max_approvals=100, window_seconds=60),
    ), secret


def _patch_get_manager(manager, queue):
    """Return a patch for _get_manager that returns the given manager and queue."""
    return patch(
        "merkaba.approval.telegram._get_manager",
        return_value=(manager, queue),
    )


@pytest.mark.asyncio
async def test_send_approval_request(action):
    from merkaba.approval.telegram import send_approval_request

    bot = AsyncMock()
    await send_approval_request(bot, chat_id=12345, action=action)

    bot.send_message.assert_called_once()
    call_kwargs = bot.send_message.call_args[1]
    assert call_kwargs["chat_id"] == 12345
    assert "send_email" in call_kwargs["text"]
    assert isinstance(call_kwargs["reply_markup"], InlineKeyboardMarkup)


@pytest.mark.asyncio
async def test_handle_approval_callback_approve(queue, manager_no_totp):
    from merkaba.approval.telegram import handle_approval_callback

    aid = queue.add_action(business_id=1, action_type="send_email", description="Test")

    query = AsyncMock()
    query.data = f"approval:approve:{aid}"
    query.message.text = "Some approval text"

    update = MagicMock()
    update.callback_query = query

    with _patch_get_manager(manager_no_totp, queue):
        # Prevent close from actually closing our test fixture
        queue_close_orig = queue.close
        queue.close = MagicMock()
        await handle_approval_callback(update, MagicMock())
        queue.close = queue_close_orig

    query.answer.assert_called_once()
    assert "Approved" in query.answer.call_args[0][0]

    action = queue.get_action(aid)
    assert action["status"] == "approved"
    assert action["decided_by"] == "telegram"


@pytest.mark.asyncio
async def test_handle_approval_callback_deny(queue, manager_no_totp):
    from merkaba.approval.telegram import handle_approval_callback

    aid = queue.add_action(business_id=1, action_type="send_email", description="Test")

    query = AsyncMock()
    query.data = f"approval:deny:{aid}"
    query.message.text = "Some approval text"

    update = MagicMock()
    update.callback_query = query

    with _patch_get_manager(manager_no_totp, queue):
        queue_close_orig = queue.close
        queue.close = MagicMock()
        await handle_approval_callback(update, MagicMock())
        queue.close = queue_close_orig

    assert "Denied" in query.answer.call_args[0][0]

    action = queue.get_action(aid)
    assert action["status"] == "denied"


@pytest.mark.asyncio
async def test_handle_callback_invalid_data():
    from merkaba.approval.telegram import handle_approval_callback

    query = AsyncMock()
    query.data = "approval:badformat"

    update = MagicMock()
    update.callback_query = query

    await handle_approval_callback(update, MagicMock())
    query.answer.assert_called_once_with("Invalid callback data")


def test_get_approval_handler():
    from merkaba.approval.telegram import get_approval_handler
    from telegram.ext import CallbackQueryHandler

    handler = get_approval_handler()
    assert isinstance(handler, CallbackQueryHandler)


def test_get_2fa_handler():
    from merkaba.approval.telegram import get_2fa_handler
    from telegram.ext import MessageHandler

    handler = get_2fa_handler()
    assert isinstance(handler, MessageHandler)


# --- 2FA Telegram flow tests ---


@pytest.mark.asyncio
async def test_high_risk_approve_prompts_2fa(queue, manager_with_totp):
    """High-risk approval triggers 2FA prompt instead of immediate approval."""
    from merkaba.approval.telegram import handle_approval_callback

    manager, secret = manager_with_totp
    aid = queue.add_action(
        business_id=1, action_type="delete_all", description="Dangerous",
        autonomy_level=4,
    )

    query = AsyncMock()
    query.data = f"approval:approve:{aid}"
    query.message.text = "Approval text"

    update = MagicMock()
    update.callback_query = query

    context = MagicMock()
    context.user_data = {}

    with _patch_get_manager(manager, queue):
        queue_close_orig = queue.close
        queue.close = MagicMock()
        await handle_approval_callback(update, context)
        queue.close = queue_close_orig

    # Should set pending_2fa state
    assert "pending_2fa" in context.user_data
    assert context.user_data["pending_2fa"]["action_id"] == aid
    # Action should still be pending
    action = queue.get_action(aid)
    assert action["status"] == "pending"


@pytest.mark.asyncio
async def test_valid_2fa_code_approves(queue, manager_with_totp):
    """Valid 6-digit code completes the 2FA approval."""
    import pyotp
    from merkaba.approval.telegram import handle_2fa_code

    manager, secret = manager_with_totp
    aid = queue.add_action(
        business_id=1, action_type="delete_all", description="Dangerous",
        autonomy_level=4,
    )

    code = pyotp.TOTP(secret).now()

    update = MagicMock()
    update.message = AsyncMock()
    update.message.text = code

    context = MagicMock()
    context.user_data = {"pending_2fa": {"action_id": aid, "timestamp": time.time()}}

    with _patch_get_manager(manager, queue):
        queue_close_orig = queue.close
        queue.close = MagicMock()
        await handle_2fa_code(update, context)
        queue.close = queue_close_orig

    # Action should be approved
    action = queue.get_action(aid)
    assert action["status"] == "approved"
    # pending_2fa should be cleared
    assert "pending_2fa" not in context.user_data


@pytest.mark.asyncio
async def test_invalid_2fa_code_rejected(queue, manager_with_totp):
    """Invalid 6-digit code shows error."""
    from merkaba.approval.telegram import handle_2fa_code

    manager, secret = manager_with_totp
    aid = queue.add_action(
        business_id=1, action_type="delete_all", description="Dangerous",
        autonomy_level=4,
    )

    update = MagicMock()
    update.message = AsyncMock()
    update.message.text = "000000"

    context = MagicMock()
    context.user_data = {"pending_2fa": {"action_id": aid, "timestamp": time.time()}}

    with _patch_get_manager(manager, queue):
        queue_close_orig = queue.close
        queue.close = MagicMock()
        await handle_2fa_code(update, context)
        queue.close = queue_close_orig

    # Action should still be pending
    action = queue.get_action(aid)
    assert action["status"] == "pending"
    # Should send error
    update.message.reply_text.assert_called_once()
    assert "Invalid" in update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_expired_2fa_rejected(queue, manager_with_totp):
    """Expired pending 2FA shows expiry message."""
    from merkaba.approval.telegram import handle_2fa_code, PENDING_2FA_TIMEOUT

    manager, secret = manager_with_totp
    aid = queue.add_action(
        business_id=1, action_type="delete_all", description="Dangerous",
        autonomy_level=4,
    )

    update = MagicMock()
    update.message = AsyncMock()
    update.message.text = "123456"

    context = MagicMock()
    context.user_data = {
        "pending_2fa": {
            "action_id": aid,
            "timestamp": time.time() - PENDING_2FA_TIMEOUT - 1,
        }
    }

    with _patch_get_manager(manager, queue):
        queue_close_orig = queue.close
        queue.close = MagicMock()
        await handle_2fa_code(update, context)
        queue.close = queue_close_orig

    # Should show expiry message
    update.message.reply_text.assert_called_once()
    assert "expired" in update.message.reply_text.call_args[0][0].lower()
    # pending_2fa should be cleared
    assert "pending_2fa" not in context.user_data


@pytest.mark.asyncio
async def test_rate_limit_blocks_telegram_approval(queue):
    """Rate limit blocks Telegram approval."""
    from merkaba.approval.telegram import handle_approval_callback
    from merkaba.approval.secure import SecureApprovalManager, RateLimitConfig

    manager = SecureApprovalManager(
        action_queue=queue,
        totp_secret=None,
        rate_limit=RateLimitConfig(max_approvals=1, window_seconds=60),
    )

    # Fill rate limit
    aid1 = queue.add_action(business_id=1, action_type="test", description="A1", autonomy_level=1)
    manager.approve(aid1, decided_by="test")

    # Try to approve another via Telegram
    aid2 = queue.add_action(business_id=1, action_type="test", description="A2", autonomy_level=1)

    query = AsyncMock()
    query.data = f"approval:approve:{aid2}"
    query.message.text = "Approval text"

    update = MagicMock()
    update.callback_query = query

    with _patch_get_manager(manager, queue):
        queue_close_orig = queue.close
        queue.close = MagicMock()
        await handle_approval_callback(update, MagicMock())
        queue.close = queue_close_orig

    # Should show rate limit message
    assert "Rate limit" in query.answer.call_args[0][0]
    # Action should still be pending
    action = queue.get_action(aid2)
    assert action["status"] == "pending"
