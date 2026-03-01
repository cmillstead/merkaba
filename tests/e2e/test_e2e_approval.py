# tests/e2e/test_e2e_approval.py
"""End-to-end tests for the approval workflow CLI commands.

Uses real SQLite databases (in temp dirs) and real CLI invocations.
Only the LLM layer is mocked (via global conftest).
"""

import pytest

pytestmark = [pytest.mark.e2e]


# ---------------------------------------------------------------------------
# 1. List empty
# ---------------------------------------------------------------------------

def test_approval_list_empty(cli_runner):
    """Fresh DB has no actions — list prints 'No actions found'."""
    runner, app = cli_runner

    result = runner.invoke(app, ["approval", "list"])
    assert result.exit_code == 0
    assert "No actions found" in result.output


# ---------------------------------------------------------------------------
# 2. Add and list
# ---------------------------------------------------------------------------

def test_approval_add_and_list(cli_runner, patched_dbs):
    """Add an action via ActionQueue, then list — it should appear."""
    runner, app = cli_runner

    from merkaba.approval.queue import ActionQueue

    queue = ActionQueue()
    action_id = queue.add_action(
        business_id=1,
        action_type="send_email",
        description="Send welcome email",
    )
    queue.close()

    result = runner.invoke(app, ["approval", "list"])
    assert result.exit_code == 0
    assert "send_email" in result.output
    assert "Send welcome email" in result.output


# ---------------------------------------------------------------------------
# 3. Approve action
# ---------------------------------------------------------------------------

def test_approval_approve_action(cli_runner, patched_dbs):
    """Add an action, approve it via CLI — verify 'Approved' in output."""
    runner, app = cli_runner

    from merkaba.approval.queue import ActionQueue

    queue = ActionQueue()
    action_id = queue.add_action(
        business_id=1,
        action_type="send_email",
        description="Send welcome email",
    )
    queue.close()

    result = runner.invoke(app, ["approval", "approve", str(action_id)])
    assert result.exit_code == 0
    assert f"Approved action #{action_id}" in result.output
    assert "send_email" in result.output


# ---------------------------------------------------------------------------
# 4. Deny action
# ---------------------------------------------------------------------------

def test_approval_deny_action(cli_runner, patched_dbs):
    """Add an action, deny it via CLI — verify 'Denied' in output."""
    runner, app = cli_runner

    from merkaba.approval.queue import ActionQueue

    queue = ActionQueue()
    action_id = queue.add_action(
        business_id=1,
        action_type="send_email",
        description="Send welcome email",
    )
    queue.close()

    result = runner.invoke(app, ["approval", "deny", str(action_id)])
    assert result.exit_code == 0
    assert f"Denied action #{action_id}" in result.output
    assert "send_email" in result.output


# ---------------------------------------------------------------------------
# 5. Approve not found
# ---------------------------------------------------------------------------

def test_approval_approve_not_found(cli_runner):
    """Approve a non-existent action ID — verify 'Cannot approve' in output."""
    runner, app = cli_runner

    result = runner.invoke(app, ["approval", "approve", "999"])
    assert result.exit_code == 0
    assert "Cannot approve" in result.output


# ---------------------------------------------------------------------------
# 6. Stats empty
# ---------------------------------------------------------------------------

def test_approval_stats_empty(cli_runner):
    """Fresh DB stats — shows the table with total count of zero."""
    runner, app = cli_runner

    result = runner.invoke(app, ["approval", "stats"])
    assert result.exit_code == 0
    assert "Approval Queue" in result.output
    assert "Total" in result.output
    assert "0" in result.output


# ---------------------------------------------------------------------------
# 7. Stats after actions
# ---------------------------------------------------------------------------

def test_approval_stats_after_actions(cli_runner, patched_dbs):
    """Add actions, approve and deny some, verify stats reflect the counts."""
    runner, app = cli_runner

    from merkaba.approval.queue import ActionQueue

    queue = ActionQueue()
    id1 = queue.add_action(business_id=1, action_type="send_email", description="Email 1")
    id2 = queue.add_action(business_id=1, action_type="send_email", description="Email 2")
    id3 = queue.add_action(business_id=1, action_type="post_update", description="Post 1")
    queue.close()

    # Approve one, deny another, leave third pending
    runner.invoke(app, ["approval", "approve", str(id1)])
    runner.invoke(app, ["approval", "deny", str(id2)])

    result = runner.invoke(app, ["approval", "stats"])
    assert result.exit_code == 0
    assert "Approval Queue" in result.output
    # Total should be 3
    assert "3" in result.output
    # Should show approved and denied counts
    assert "Approved" in result.output
    assert "Denied" in result.output
    assert "Pending" in result.output


# ---------------------------------------------------------------------------
# 8. Graduation no suggestions
# ---------------------------------------------------------------------------

def test_approval_graduation_no_suggestions(cli_runner):
    """Fresh business with no approval history — graduation shows no suggestions."""
    runner, app = cli_runner

    # Create a business first so the ID exists
    runner.invoke(app, ["business", "add", "--name", "Test", "--type", "ecommerce"])

    result = runner.invoke(app, ["approval", "graduation", "1"])
    assert result.exit_code == 0
    assert "No action types ready" in result.output
