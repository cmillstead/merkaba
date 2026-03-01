"""Telegram bot integration for Merkaba."""

from merkaba.telegram.config import TelegramConfig

__all__ = ["TelegramConfig", "MerkabaBot"]


def __getattr__(name):
    if name == "MerkabaBot":
        from merkaba.telegram.bot import MerkabaBot
        return MerkabaBot
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
