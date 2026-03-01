"""Telegram bot integration for Friday."""

from friday.telegram.config import TelegramConfig

__all__ = ["TelegramConfig", "FridayBot"]


def __getattr__(name):
    if name == "FridayBot":
        from friday.telegram.bot import FridayBot
        return FridayBot
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
