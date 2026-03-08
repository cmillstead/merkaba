# src/merkaba/approval/graduation.py
import logging
from dataclasses import dataclass

from merkaba.approval.queue import ActionQueue

logger = logging.getLogger(__name__)

DEFAULT_GRADUATION_THRESHOLD = 5


@dataclass
class GraduationChecker:
    """Checks whether an action_type has earned enough trust to be promoted."""

    action_queue: ActionQueue
    threshold: int = DEFAULT_GRADUATION_THRESHOLD

    def check(self, business_id: int, action_type: str) -> dict | None:
        """Check if action_type qualifies for promotion.

        Returns a promotion suggestion dict, or None.
        """
        stats = self.action_queue.get_stats(business_id, action_type)
        if not stats:
            return None

        stat = stats[0]
        approved = stat["approved_count"]
        denied = stat["denied_count"]

        if denied > 0:
            return None

        if approved >= self.threshold:
            try:
                from merkaba.observability.audit import record_decision
                record_decision(
                    decision_type="graduation_suggestion",
                    decision=f"promote_{action_type}",
                    alternatives=["promote", "keep_current"],
                    context_summary=f"business={business_id}, approved={approved}, denied={denied}",
                )
            except Exception as e:
                logger.debug("Failed to record graduation suggestion: %s", e, exc_info=True)
            return {
                "business_id": business_id,
                "action_type": action_type,
                "approved_count": approved,
                "denied_count": denied,
                "suggestion": (
                    f"Promote '{action_type}' from ask -> notify? "
                    f"({approved} consecutive approvals, 0 denials)"
                ),
            }

        return None

    def check_all(self, business_id: int) -> list[dict]:
        """Check all action types for a business. Returns list of suggestions."""
        all_stats = self.action_queue.get_stats(business_id)
        suggestions = []
        for stat in all_stats:
            result = self.check(business_id, stat["action_type"])
            if result:
                suggestions.append(result)
        return suggestions
