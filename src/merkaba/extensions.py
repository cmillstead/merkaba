"""Discover and load workers, adapters, and CLI apps from installed packages."""

import importlib.metadata
import logging

logger = logging.getLogger(__name__)


def _get_entry_points(group: str):
    """Return entry points for a group. Wrapper for testability."""
    return importlib.metadata.entry_points(group=group)


def discover_workers():
    """Load workers from installed packages declaring merkaba.workers entry points."""
    from merkaba.orchestration.workers import register_worker

    for ep in _get_entry_points("merkaba.workers"):
        try:
            cls = ep.load()
            register_worker(ep.name, cls)
            logger.info("Loaded worker extension: %s", ep.name)
        except Exception as e:
            logger.warning("Failed to load worker %s: %s", ep.name, e)


def discover_adapters():
    """Load adapters from installed packages declaring merkaba.adapters entry points."""
    from merkaba.integrations.base import register_adapter

    for ep in _get_entry_points("merkaba.adapters"):
        try:
            cls = ep.load()
            register_adapter(ep.name, cls)
            logger.info("Loaded adapter extension: %s", ep.name)
        except Exception as e:
            logger.warning("Failed to load adapter %s: %s", ep.name, e)


def discover_cli_apps() -> dict:
    """Load CLI subcommand apps from installed packages declaring merkaba.cli entry points."""
    apps = {}
    for ep in _get_entry_points("merkaba.cli"):
        try:
            apps[ep.name] = ep.load()
            logger.info("Loaded CLI extension: %s", ep.name)
        except Exception as e:
            logger.warning("Failed to load CLI extension %s: %s", ep.name, e)
    return apps
