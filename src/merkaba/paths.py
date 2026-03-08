"""Centralised filesystem paths for Merkaba.

All code that needs to resolve ``~/.merkaba`` (or a subdirectory / file
inside it) should import helpers from this module instead of scattering
``os.path.expanduser("~/.merkaba")`` throughout the codebase.

The ``MERKABA_HOME`` environment variable, when set, overrides the
default ``~/.merkaba`` location.  This is useful for tests, CI, and
running multiple Merkaba instances side by side.
"""

import os


def merkaba_home() -> str:
    """Return the Merkaba data directory, honouring MERKABA_HOME env var."""
    return os.environ.get("MERKABA_HOME") or os.path.expanduser("~/.merkaba")


def config_path() -> str:
    """Return the path to config.json."""
    return os.path.join(merkaba_home(), "config.json")


def db_path(name: str) -> str:
    """Return path to a named database file.

    Example::

        db_path("memory")   # -> "~/.merkaba/memory.db"
        db_path("tasks")    # -> "~/.merkaba/tasks.db"
    """
    return os.path.join(merkaba_home(), f"{name}.db")


def subdir(name: str) -> str:
    """Return path to a subdirectory inside the Merkaba home.

    Example::

        subdir("conversations")  # -> "~/.merkaba/conversations"
        subdir("plugins")        # -> "~/.merkaba/plugins"
    """
    return os.path.join(merkaba_home(), name)
