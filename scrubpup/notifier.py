"""Alerts via terminal, SMTP email, Discord webhook and Slack webhook.

Configured in ``protected.yaml`` under ``settings.notifier``::

    notifier:
      terminal: true
      email:
        smtp_host: smtp.example.com
        smtp_port: 587
        username: me@example.com
        password_env: SCRUBPUP_SMTP_PASSWORD
        from: me@example.com
        to: me@example.com
      discord_webhook: https://discord.com/api/webhooks/...
      slack_webhook: https://hooks.slack.com/services/...
"""

from __future__ import annotations

import json
import os
import smtplib
from email.message import EmailMessage

import requests

from .utils import get_logger

log = get_logger("scrubpup.notifier")

EVENTS = ("new_exposure", "optout_completed", "scan_completed")


class Notifier:
    def __init__(self, settings: dict | None = None) -> None:
        self.settings = settings or {}

    def notify(self, event: str, title: str, body: str) -> list[str]:
        """Send an alert through every configured channel; returns channels used."""
        used: list[str] = []
        if self.settings.get("terminal", True):
            self._terminal(title, body)
            used.append("terminal")
        if self.settings.get("email") and self._email(title, body):
            used.append("email")
        discord = self.settings.get("discord_webhook")
        if discord and self._webhook(discord, {"content": f"**{title}**\n{body}"}):
            used.append("discord")
        slack = self.settings.get("slack_webhook")
        if slack and self._webhook(slack, {"text": f"*{title}*\n{body}"}):
            used.append("slack")
        log.info("notified event=%s via %s", event, ",".join(used) or "nothing")
        return used

    @staticmethod
    def _terminal(title: str, body: str) -> None:
        print(f"\n=== {title} ===\n{body}\n")

    def _email(self, title: str, body: str) -> bool:
        cfg = self.settings.get("email") or {}
        host, to = cfg.get("smtp_host"), cfg.get("to")
        if not host or not to:
            log.warning("email notifier misconfigured (smtp_host/to missing)")
            return False
        msg = EmailMessage()
        msg["Subject"] = f"[ScrubPup] {title}"
        msg["From"] = cfg.get("from", cfg.get("username", "scrubpup@localhost"))
        msg["To"] = to
        msg.set_content(body)
        password = os.environ.get(cfg.get("password_env", "SCRUBPUP_SMTP_PASSWORD"), "")
        try:
            with smtplib.SMTP(host, int(cfg.get("smtp_port", 587)), timeout=20) as smtp:
                smtp.starttls()
                if cfg.get("username"):
                    smtp.login(cfg["username"], password)
                smtp.send_message(msg)
        except (OSError, smtplib.SMTPException) as exc:
            log.warning("email notification failed: %s", exc)
            return False
        return True

    @staticmethod
    def _webhook(url: str, payload: dict) -> bool:
        try:
            resp = requests.post(
                url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=15,
            )
        except requests.RequestException as exc:
            log.warning("webhook notification failed: %s", exc)
            return False
        return resp.status_code < 300
