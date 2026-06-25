"""Send HTML reports over generic SMTP (defaults suit Gmail/Workspace)."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from .config import SmtpConfig

logger = logging.getLogger(__name__)


class Mailer:
    def __init__(self, config: SmtpConfig) -> None:
        self._config = config

    def send_html(self, *, to: list[str], subject: str, html: str) -> None:
        if not to:
            raise ValueError("No recipients configured")
        if not self._config.from_address:
            raise ValueError("smtp.from_address is not configured")

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self._config.from_address
        msg["To"] = ", ".join(to)
        msg.set_content(
            "This report is best viewed as HTML. "
            "Your client does not support HTML email."
        )
        msg.add_alternative(html, subtype="html")

        logger.info(
            "Sending '%s' to %s via %s:%d",
            subject,
            to,
            self._config.host,
            self._config.port,
        )
        with smtplib.SMTP(self._config.host, self._config.port, timeout=30) as smtp:
            smtp.ehlo()
            if self._config.use_starttls:
                smtp.starttls()
                smtp.ehlo()
            if self._config.username:
                smtp.login(self._config.username, self._config.password or "")
            smtp.send_message(msg)
