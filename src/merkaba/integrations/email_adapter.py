# src/friday/integrations/email_adapter.py
"""Email integration adapter — SMTP send, IMAP read, LLM-based parse."""

import email
import imaplib
import json
import logging
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Any

from friday.integrations.base import IntegrationAdapter, register_adapter
from friday.integrations.credentials import CredentialManager

logger = logging.getLogger(__name__)

REQUIRED_CREDENTIALS = [
    "smtp_host", "smtp_port", "smtp_user", "smtp_password",
    "imap_host", "imap_user", "imap_password",
]


@dataclass
class EmailAdapter(IntegrationAdapter):
    """Email adapter: send via SMTP, read via IMAP, parse via LLM."""

    _creds: CredentialManager = field(default_factory=CredentialManager, init=False, repr=False)
    _config: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    _llm: Any = field(default=None, init=False, repr=False)

    def connect(self) -> bool:
        ok, missing = self._creds.has_required("email", REQUIRED_CREDENTIALS)
        if not ok:
            logger.warning("Email adapter missing credentials: %s", missing)
            self._connected = False
            return False
        self._config = {k: self._creds.get("email", k) for k in REQUIRED_CREDENTIALS}
        self._connected = True
        return True

    def execute(self, action: str, params: dict | None = None) -> dict:
        params = params or {}
        if action == "send":
            return self._send(params)
        elif action == "read_inbox":
            return self._read_inbox(params)
        elif action == "parse_email":
            return self._parse_email(params)
        else:
            return {"ok": False, "error": f"Unknown action: {action}"}

    def health_check(self) -> dict:
        return {"ok": self._connected, "adapter": "email"}

    def _send(self, params: dict) -> dict:
        required = {"to", "subject", "body"}
        if not required.issubset(params.keys()):
            missing = required - params.keys()
            return {"ok": False, "error": f"Missing required params: {missing}"}

        msg = EmailMessage()
        msg["From"] = self._config["smtp_user"]
        msg["To"] = params["to"]
        msg["Subject"] = params["subject"]
        msg.set_content(params["body"])

        if params.get("html"):
            msg.add_alternative(params["html"], subtype="html")

        try:
            port = int(self._config["smtp_port"])
        except (ValueError, TypeError):
            return {"ok": False, "error": f"Invalid smtp_port: {self._config.get('smtp_port')}"}

        try:
            with smtplib.SMTP(self._config["smtp_host"], port) as server:
                server.starttls()
                server.login(self._config["smtp_user"], self._config["smtp_password"])
                server.send_message(msg)
            return {"ok": True, "to": params["to"], "subject": params["subject"]}
        except Exception as e:
            logger.error("Email send failed: %s", e)
            return {"ok": False, "error": str(e)}

    def _read_inbox(self, params: dict) -> dict:
        folder = params.get("folder", "INBOX")
        limit = params.get("limit", 10)
        unread_only = params.get("unread_only", True)

        try:
            imap = imaplib.IMAP4_SSL(self._config["imap_host"])
            imap.login(self._config["imap_user"], self._config["imap_password"])
            imap.select(folder)

            criteria = "UNSEEN" if unread_only else "ALL"
            _, msg_ids = imap.search(None, criteria)
            ids = msg_ids[0].split() if msg_ids[0] else []
            ids = ids[-limit:]

            emails = []
            for mid in ids:
                _, data = imap.fetch(mid, "(RFC822)")
                if not data or not data[0]:
                    continue
                try:
                    raw = data[0] if isinstance(data[0], bytes) else data[0][1]
                except (IndexError, TypeError):
                    continue

                msg = email.message_from_bytes(raw)
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode(errors="replace")
                            break
                else:
                    body = msg.get_payload(decode=True).decode(errors="replace")

                emails.append({
                    "from": msg.get("From", ""),
                    "subject": msg.get("Subject", ""),
                    "date": msg.get("Date", ""),
                    "body": body[:2000],
                })

            imap.logout()
            return {"ok": True, "emails": emails, "count": len(emails)}
        except Exception as e:
            logger.error("Email read failed: %s", e)
            return {"ok": False, "error": str(e), "emails": []}

    def _parse_email(self, params: dict) -> dict:
        required = {"body"}
        if not required.issubset(params.keys()):
            return {"ok": False, "error": "Missing required param: body"}

        prompt = (
            f"From: {params.get('from', 'unknown')}\n"
            f"Subject: {params.get('subject', 'none')}\n"
            f"Body:\n{params['body'][:2000]}\n\n"
            "Extract structured data from this email. Respond in JSON with these fields:\n"
            '{"intent": "order_inquiry|complaint|question|spam|other", '
            '"order_id": "if mentioned", "customer": "name if found", '
            '"urgency": "low|medium|high", "summary": "one sentence"}'
        )

        try:
            llm = self._get_llm()
            response = llm.chat(
                message=prompt,
                system_prompt="You extract structured data from emails. Respond only in valid JSON.",
            )
            parsed = json.loads(response.content)
            return {"ok": True, "parsed": parsed}
        except (json.JSONDecodeError, TypeError):
            return {"ok": False, "parsed": {"raw_response": response.content if response else ""}}
        except Exception as e:
            logger.error("Email parse failed: %s", e)
            return {"ok": False, "error": str(e)}

    def _get_llm(self):
        if self._llm is None:
            from friday.llm import LLMClient
            self._llm = LLMClient()
        return self._llm


register_adapter("email", EmailAdapter)
