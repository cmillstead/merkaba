import logging

from merkaba.integrations.base import (
    IntegrationAdapter,
    ADAPTER_REGISTRY,
    register_adapter,
    get_adapter_class,
    list_adapters,
)
from merkaba.integrations.credentials import CredentialManager

logger = logging.getLogger(__name__)

# Import adapters to trigger registration
from merkaba.integrations import email_adapter  # noqa: F401
from merkaba.integrations import stripe_adapter  # noqa: F401

try:
    from merkaba.integrations import slack_adapter  # noqa: F401
except ImportError:
    logger.debug("slack_sdk not installed -- Slack adapter unavailable")

try:
    from merkaba.integrations import github_adapter  # noqa: F401
except ImportError:
    logger.debug("PyGithub not installed -- GitHub adapter unavailable")

try:
    from merkaba.integrations import calendar_adapter  # noqa: F401
except ImportError:
    logger.debug("pyobjc-framework-EventKit not installed -- Calendar adapter unavailable")

try:
    from merkaba.integrations import discord_adapter  # noqa: F401
except ImportError:
    logger.debug("discord.py not installed -- Discord adapter unavailable")

try:
    from merkaba.integrations import qmd_adapter  # noqa: F401
except ImportError:
    logger.debug("QMD not available -- QMD adapter unavailable")

# signal-cli is an external system binary, not a pip package.
# The adapter always loads; connect() checks for the binary at runtime.
from merkaba.integrations import signal_adapter  # noqa: F401

__all__ = [
    "IntegrationAdapter",
    "ADAPTER_REGISTRY",
    "register_adapter",
    "get_adapter_class",
    "list_adapters",
    "CredentialManager",
]
