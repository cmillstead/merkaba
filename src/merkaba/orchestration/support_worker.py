# src/merkaba/orchestration/support_worker.py
"""Support domain worker — handles ticket triage, response drafting, escalation, and satisfaction analysis."""

import json
import logging
from dataclasses import dataclass

from merkaba.orchestration.workers import Worker, WorkerResult, register_worker

logger = logging.getLogger(__name__)


@dataclass
class SupportWorker(Worker):
    """Handles support tasks: triage tickets, draft responses, escalate, and analyze satisfaction."""

    def execute(self, task: dict) -> WorkerResult:
        payload = task.get("payload") or {}
        action = payload.get("action")

        actions = {
            "triage_ticket": self._triage_ticket,
            "draft_response": self._draft_response,
            "escalate_ticket": self._escalate_ticket,
            "analyze_satisfaction": self._analyze_satisfaction,
        }

        handler = actions.get(action)
        if handler is None:
            return WorkerResult(
                success=False,
                output={},
                error=f"Unknown support action: {action}",
            )

        try:
            return handler(task, payload)
        except Exception as e:
            logger.error("SupportWorker error on %s: %s", action, e)
            return WorkerResult(success=False, output={}, error=str(e))

    # --- Actions ---

    def _triage_ticket(self, task: dict, payload: dict) -> WorkerResult:
        """LLM classifies ticket priority and category from description."""
        description = payload.get("description", "")
        ticket_id = payload.get("ticket_id", "unknown")
        context = self._build_context(task)
        prompt = (
            f"{context}\n\n"
            f"Triage the following support ticket:\n\n{description}\n\n"
            "Classify the ticket by priority (low/medium/high/critical) and category.\n"
            'Respond in JSON: {{"priority": "...", "category": "...", "summary": "..."}}'
        )

        response = self._ask_llm(
            prompt,
            system_prompt="You are an experienced support agent. Classify tickets accurately by urgency and topic.",
        )

        try:
            data = json.loads(response)
        except (json.JSONDecodeError, TypeError):
            data = {"priority": "medium", "category": "general", "summary": response}

        return WorkerResult(
            success=True,
            output=data,
            facts_learned=[{
                "category": "support",
                "key": f"ticket:{ticket_id}",
                "value": json.dumps(data),
            }],
        )

    def _draft_response(self, task: dict, payload: dict) -> WorkerResult:
        """LLM drafts a response to a support ticket."""
        ticket = payload.get("ticket", {})
        ticket_id = ticket.get("ticket_id", payload.get("ticket_id", "unknown"))
        description = ticket.get("description", "")
        context_info = ticket.get("context", "")
        prompt = (
            f"Support ticket:\n{description}\n\n"
            f"Additional context:\n{context_info}\n\n"
            "Draft a helpful, empathetic response to this support ticket.\n"
            'Respond in JSON: {{"response": "...", "tone": "...", "follow_up_needed": true/false}}'
        )

        response = self._ask_llm(
            prompt,
            system_prompt="You are a skilled support representative. Write clear, empathetic, and helpful responses.",
        )

        try:
            data = json.loads(response)
        except (json.JSONDecodeError, TypeError):
            data = {"response": response, "tone": "neutral", "follow_up_needed": False}

        return WorkerResult(
            success=True,
            output=data,
            facts_learned=[{
                "category": "support",
                "key": f"response:{ticket_id}",
                "value": json.dumps(data),
            }],
        )

    def _escalate_ticket(self, task: dict, payload: dict) -> WorkerResult:
        """Route ticket to approval queue for human escalation."""
        required = {"ticket_id", "reason"}
        missing = required - set(payload.keys())

        if missing:
            return WorkerResult(
                success=False,
                output={},
                error=f"Missing escalation params: {missing}",
            )

        return WorkerResult(
            success=True,
            output={"ticket_id": payload["ticket_id"], "status": "pending_approval"},
            needs_approval=[{
                "action_type": "escalate_ticket",
                "description": f"Escalate ticket {payload['ticket_id']}: {payload['reason']}",
                "autonomy_level": 1,
                "params": {
                    "ticket_id": payload["ticket_id"],
                    "reason": payload["reason"],
                },
            }],
            decisions_made=[{
                "action_type": "escalate_ticket",
                "decision": f"Proposed escalation for ticket {payload['ticket_id']}",
                "reasoning": payload["reason"],
            }],
        )

    def _analyze_satisfaction(self, task: dict, payload: dict) -> WorkerResult:
        """LLM analyzes support interaction quality and returns recommendations."""
        context = self._build_context(task)
        prompt = (
            f"{context}\n\n"
            "Analyze the quality of support interactions based on the context above.\n"
            "Consider response times, resolution rates, and customer sentiment.\n\n"
            'Respond in JSON: {{"satisfaction_summary": "...", '
            '"recommendations": [{{"action": "...", "reasoning": "..."}}]}}'
        )

        response = self._ask_llm(
            prompt,
            system_prompt="You are a support quality analyst. Provide actionable insights to improve customer satisfaction.",
        )

        try:
            data = json.loads(response)
        except (json.JSONDecodeError, TypeError):
            data = {"raw_response": response}

        recommendations = data.get("recommendations", [])
        decisions = [
            {
                "action_type": "satisfaction_analysis",
                "decision": r.get("action", "No action"),
                "reasoning": r.get("reasoning", "LLM recommendation"),
            }
            for r in recommendations
        ]

        return WorkerResult(
            success=True,
            output=data,
            decisions_made=decisions,
        )


register_worker("support", SupportWorker)
