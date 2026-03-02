# src/merkaba/orchestration/heartbeat_checklist.py
"""Parser for HEARTBEAT.md files — user-editable checklists.

Format:
    - [ ] Description (schedule)
    - [x] Description (schedule)   # already done

The schedule in parentheses is optional. Supported formats:
    every 30m, every 1h, daily, weekly, hourly
"""

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ChecklistItem:
    description: str
    schedule: str | None
    checked: bool


# Matches:  - [ ] or - [x]  then description  then optional (schedule)
_CHECKLIST_RE = re.compile(
    r"^-\s+\[([ xX])\]\s+"  # checkbox
    r"(.+?)"  # description (non-greedy)
    r"(?:\s+\(([^)]+)\))?"  # optional (schedule)
    r"\s*$"  # end of line
)


def parse_heartbeat_md(path: Path) -> list[ChecklistItem]:
    """Parse a HEARTBEAT.md file into checklist items.

    Returns empty list if file doesn't exist or is unparseable.
    """
    try:
        text = path.read_text()
    except (FileNotFoundError, OSError):
        return []

    items = []
    for line in text.splitlines():
        m = _CHECKLIST_RE.match(line.strip())
        if m:
            checked = m.group(1).lower() == "x"
            description = m.group(2).strip()
            schedule = m.group(3).strip() if m.group(3) else None
            items.append(
                ChecklistItem(
                    description=description,
                    schedule=schedule,
                    checked=checked,
                )
            )
    return items
