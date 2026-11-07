"""Envio de e-mails: Console (simulação/registro), SMTP (IMAP/Gmail) ou Graph (Microsoft)."""
from __future__ import annotations

import logging
import smtplib
import ssl
from abc import ABC, abstractmethod
from functools import lru_cache

from app.config import Settings, settings
from app.email.mime import build_message

log = logging.getLogger("nova.mail")


class MailGateway(ABC):
    @abstractmethod
    def send_reply(self, *, graph_id: str | None, from_email: str, to: str,
                   subject: str, body: str, references: str | None = None) -> None: ...

    @abstractmethod
    def send_mail(self, *, to: str, subject: str, body: str) -> None: ...


class ConsoleMailGateway(MailGateway):
    def __init__(self) -> None:
        self.outbox: list[dict] = []

    def _store(self, kind: str, to: str, subject: str, body: str, references: str | None = None) -> None:
        self.outbox.append({"type": kind, "to": to, "subject": subject, "body": body, "references": references})
        log.info("[SIMULADO] %s para %s | %s", kind, to, subject)

    def send_reply(self, *, graph_id, from_email, to, subject, body, references=None) -> None:
        self._store("reply", to, subject, body, references=references)

    def send_mail(self, *, to, subject, body) -> None:
        self._store("mail", to, subject, body)


class SmtpMailGateway(MailGateway):
    def __init__(self, s: Settings) -> None:
        self.host, self.port = s.smtp_host, s.smtp_port
        self.username = s.mail_username
        self.password = s.mail_password.replace(" ", "")
        self.sender = s.nova_email or s.mail_username
        self.sender_name = s.from_name
        self.reply_to = s.reply_to or None

    def _send(self, msg) -> None:
        if self.port == 465:
            server = smtplib.SMTP_SSL(self.host, self.port, timeout=30,
                                      context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(self.host, self.port, timeout=30)
        with server as smtp:
            if self.port != 465:
                smtp.starttls(context=ssl.create_default_context())
            smtp.login(self.username, self.password)
            smtp.send_message(msg)

    def send_reply(self, *, graph_id, from_email, to, subject, body, references=None) -> None:
        self._send(build_message(sender=self.sender, to=to, subject=subject, body=body,
                                 in_reply_to=graph_id, references=references, reply_to=self.reply_to,
                                 sender_name=self.sender_name))

    def send_mail(self, *, to, subject, body) -> None:
        self._send(build_message(sender=self.sender, to=to, subject=subject, body=body,
                                 auto_submitted="auto-generated", reply_to=self.reply_to,
                                 sender_name=self.sender_name))


class GraphMailGateway(MailGateway):
    def __init__(self, graph) -> None:
        self.graph = graph

    def send_reply(self, *, graph_id, from_email, to, subject, body, references=None) -> None:
        from app.microsoft.graph import text_to_html

        # O endpoint de reply do Graph já cuida do threading (In-Reply-To/References)
        # sozinho, então `references` não é usado aqui — só existe pra manter a
        # mesma assinatura do SmtpMailGateway.
        html_body = text_to_html(body)
        if graph_id and to.lower() == from_email.lower():
            self.graph.reply(graph_id, html_body)
        else:
            self.graph.send_mail(to=to, subject=subject, html_body=html_body)

    def send_mail(self, *, to, subject, body) -> None:
        from app.microsoft.graph import text_to_html

        self.graph.send_mail(to=to, subject=subject, html_body=text_to_html(body))


@lru_cache
def get_mail_gateway() -> MailGateway:
    if settings.mail_mode == "graph":
        from app.microsoft.graph import build_graph_client

        return GraphMailGateway(build_graph_client())
    if settings.mail_mode == "imap":
        return SmtpMailGateway(settings)
    return ConsoleMailGateway()
