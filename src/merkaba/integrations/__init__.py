import logging

from friday.integrations.base import (
    IntegrationAdapter,
    ADAPTER_REGISTRY,
    register_adapter,
    get_adapter_class,
    list_adapters,
)
from friday.integrations.credentials import CredentialManager

logger = logging.getLogger(__name__)

# Import adapters to trigger registration
from friday.integrations import email_adapter  # noqa: F401
from friday.integrations import stripe_adapter  # noqa: F401
from friday.integrations import etsy_adapter  # noqa: F401

try:
    from friday.integrations import slack_adapter  # noqa: F401
except ImportError:
    logger.debug("slack_sdk not installed — Slack adapter unavailable")

try:
    from friday.integrations import github_adapter  # noqa: F401
except ImportError:
    logger.debug("PyGithub not installed — GitHub adapter unavailable")

try:
    from friday.integrations import twitter_adapter  # noqa: F401
except ImportError:
    logger.debug("tweepy not installed — Twitter adapter unavailable")

try:
    from friday.integrations import calendar_adapter  # noqa: F401
except ImportError:
    logger.debug("pyobjc-framework-EventKit not installed — Calendar adapter unavailable")

__all__ = [
    "IntegrationAdapter",
    "ADAPTER_REGISTRY",
    "register_adapter",
    "get_adapter_class",
    "list_adapters",
    "CredentialManager",
]
