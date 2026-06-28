"""Send HTML reports over generic SMTP (defaults suit Gmail/Workspace)."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from .config import SmtpConfig
from .images import InlineImage

logger = logging.getLogger(__name__)


class Mailer:
    def __init__(self, config: SmtpConfig) -> None:
        self._config = config

    def send_html(
        self,
        *,
        to: list[str],
        subject: str,
        html: str,
        inline_images: list[InlineImage] | None = None,
    ) -> None:
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

        if inline_images:
            # The HTML alternative is the last payload; attach images to it as
            # related parts so cid: references resolve inside the message.
            html_part = msg.get_payload()[-1]
            for img in inline_images:
                html_part.add_related(
                    img.data,
                    maintype=img.maintype,
                    subtype=img.subtype,
                    cid=f"<{img.cid}>",
                )

        size_mb = len(bytes(msg)) / 1_000_000
        logger.info(
            "Sending '%s' (%.1f MB) to %s via %s:%d",
            subject,
            size_mb,
            to,
            self._config.host,
            self._config.port,
        )
        if size_mb > 25:
            logger.warning(
                "Message is %.1f MB, above Gmail's 25 MB limit; it may be "
                "rejected. Consider --no-embed-images.",
                size_mb,
            )
        with smtplib.SMTP(
            self._config.host, self._config.port, timeout=self._config.timeout_seconds
        ) as smtp:
            smtp.ehlo()
            if self._config.use_starttls:
                smtp.starttls()
                smtp.ehlo()
            if self._config.username:
                smtp.login(self._config.username, self._config.password or "")
            smtp.send_message(msg)
