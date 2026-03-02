# src/merkaba/orchestration/session.py


def build_session_id(
    channel: str,
    sender_id: str,
    topic_id: str | None = None,
    business_id: str | None = None,
) -> str:
    """Build a scoped session ID.

    Format: channel:sender_id[:topic:topic_id][:biz:business_id]

    Includes topic_id to prevent context bleeding across topics
    (known ZeroClaw bug: channel + sender only, no topic awareness).
    """
    parts = [channel, sender_id]
    if topic_id:
        parts.append(f"topic:{topic_id}")
    if business_id:
        parts.append(f"biz:{business_id}")
    return ":".join(parts)
