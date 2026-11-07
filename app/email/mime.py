"""Montagem das mensagens enviadas por SMTP (sem rede, fácil de testar)."""
from __future__ import annotations

from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid


def build_message(
    *,
    sender: str,
    to: str,
    subject: str,
    body: str,
    in_reply_to: str | None = None,
    references: str | None = None,
    auto_submitted: str = "auto-replied",
    reply_to: str | None = None,
    sender_name: str = "",
) -> EmailMessage:
    """Cria o e-mail. Os cabeçalhos Auto-Submitted evitam laços entre robôs (RFC 3834).

    `references` deve ser a cadeia ACUMULADA da conversa (o References do
    e-mail original + o Message-ID dele), não só o Message-ID do e-mail
    respondido. Do contrário, cada volta da conversa "esquece" a raiz da
    thread e o cliente respondendo de novo vira uma conversa nova aos olhos
    da NOVA (ver EmailProcessor._reply)."""
    msg = EmailMessage()
    msg["From"] = formataddr((sender_name, sender)) if sender_name else sender
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender.partition("@")[2] or None)
    msg["Auto-Submitted"] = auto_submitted
    msg["X-Auto-Response-Suppress"] = "All"
    if in_reply_to and in_reply_to.startswith("<"):
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = references or in_reply_to
    msg.set_content(body)
    return msg
