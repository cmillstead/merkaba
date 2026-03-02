# tests/test_heartbeat_checklist.py
from merkaba.orchestration.heartbeat_checklist import parse_heartbeat_md, ChecklistItem


def test_parse_basic_items(tmp_path):
    md = tmp_path / "HEARTBEAT.md"
    md.write_text(
        "# Heartbeat Checklist\n\n"
        "- [ ] Check email (every 30m)\n"
        "- [x] Run backup (daily)\n"
        "- [ ] Review approvals\n"
    )
    items = parse_heartbeat_md(md)
    assert len(items) == 3
    assert items[0].description == "Check email"
    assert items[0].schedule == "every 30m"
    assert not items[0].checked
    assert items[1].checked
    assert items[2].schedule is None


def test_parse_missing_file(tmp_path):
    items = parse_heartbeat_md(tmp_path / "nope.md")
    assert items == []


def test_parse_ignores_non_checklist_lines(tmp_path):
    md = tmp_path / "HEARTBEAT.md"
    md.write_text(
        "# Heartbeat\n\n"
        "Some description text.\n\n"
        "- [ ] Actual item (every 1h)\n"
        "- Not a checklist item\n"
    )
    items = parse_heartbeat_md(md)
    assert len(items) == 1
