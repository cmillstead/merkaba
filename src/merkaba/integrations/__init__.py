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
    from merkaba.integrations import qmd_adapter  # noqa: F401
except ImportError:
    logger.debug("QMD not available -- QMD adapter unavailable")

__all__ = [
    "IntegrationAdapter",
    "ADAPTER_REGISTRY",
    "register_adapter",
    "get_adapter_class",
    "list_adapters",
    "CredentialManager",
]
