"""Transforma a mensagem do Microsoft Graph em IncomingEmail e limpa o corpo."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from email import message_from_bytes, policy
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from html.parser import HTMLParser

from app.email.models import IncomingEmail

_BLOCK_TAGS = {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6"}
_HEADER_FOLLOW = re.compile(r"^\s*(Enviado|Sent|Para|To|Assunto|Subject|Date|Data)\s*:", re.I)
_QUOTE_START = [
    re.compile(r"^\s*Em .{5,200}escreveu:\s*$", re.I),
    re.compile(r"^\s*On .{5,200}wrote:\s*$", re.I),
    re.compile(r"^\s*-{2,}\s*(Original Message|Mensagem original)\s*-{2,}\s*$", re.I),
    re.compile(r"^\s*_{10,}\s*$"),
]
_FROM_LINE = re.compile(r"^\s*(De|From)\s*:", re.I)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html or "")
    text = "".join(parser.parts).replace("\xa0", " ")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _is_quote_start(lines: list[str], i: int) -> bool:
    line = lines[i]
    if any(p.match(line) for p in _QUOTE_START):
        return True
    if _FROM_LINE.match(line):
        # "De:" só conta se vier acompanhado de Enviado/Para/Assunto logo abaixo
        return any(_HEADER_FOLLOW.match(x) for x in lines[i + 1:i + 4])
    return False


def clean_body(text: str) -> str:
    """Remove a parte citada (respostas anteriores) do corpo do e-mail."""
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = raw.split("\n")
    out: list[str] = []
    for i, line in enumerate(lines):
        if _is_quote_start(lines, i):
            break
        if line.lstrip().startswith(">"):
            continue
        out.append(line)
    cleaned = "\n".join(out).strip()
    return cleaned or raw.strip()


def _addr(obj: dict | None) -> str:
    return ((obj or {}).get("emailAddress") or {}).get("address", "") or ""


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def parse_graph_message(msg: dict) -> IncomingEmail:
    headers = {
        h.get("name", "").lower(): h.get("value", "")
        for h in (msg.get("internetMessageHeaders") or [])
    }
    body = msg.get("body") or {}
    content = body.get("content", "") or ""
    if (body.get("contentType") or "").lower() == "html":
        content = html_to_text(content)

    sender = msg.get("from") or msg.get("sender")
    return IncomingEmail(
        message_id=(msg.get("internetMessageId") or msg["id"]),
        graph_id=msg.get("id", ""),
        conversation_id=msg.get("conversationId", "") or "",
        from_email=_addr(sender),
        from_name=((sender or {}).get("emailAddress") or {}).get("name", "") or "",
        reply_to=[_addr(r) for r in (msg.get("replyTo") or [])],
        to=[_addr(r) for r in (msg.get("toRecipients") or [])],
        cc=[_addr(r) for r in (msg.get("ccRecipients") or [])],
        return_path=headers.get("return-path", "").strip("<> "),
        subject=msg.get("subject", "") or "",
        body=clean_body(content),
        received_at=_parse_dt(msg.get("receivedDateTime")),
        headers=headers,
    )


def parse_rfc822(raw: bytes, fallback_id: str = "") -> IncomingEmail:
    """Converte um e-mail bruto (IMAP) em IncomingEmail.

    A conversa (conversation_id) é a raiz da thread: o primeiro Message-ID de
    References; se não houver, o In-Reply-To; senão o próprio Message-ID.
    Assim, a resposta do cliente com o CNPJ cai na mesma conversa do pedido original.
    """
    msg = message_from_bytes(raw, policy=policy.default)
    message_id = str(msg.get("Message-ID") or "").strip() or f"<imap-{fallback_id}@local>"
    name, address = parseaddr(str(msg.get("From") or ""))
    reply_to = [a for _, a in getaddresses([str(v) for v in msg.get_all("Reply-To", [])])]
    to = [a for _, a in getaddresses([str(v) for v in msg.get_all("To", [])])]
    cc = [a for _, a in getaddresses([str(v) for v in msg.get_all("Cc", [])])]

    content = ""
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is not None:
        content = part.get_content()
        if part.get_content_type() == "text/html":
            content = html_to_text(content)

    refs = str(msg.get("References") or "").split()
    in_reply_to = str(msg.get("In-Reply-To") or "").strip()
    conversation = refs[0] if refs else (in_reply_to or message_id)

    try:
        received = parsedate_to_datetime(str(msg.get("Date")))
        if received.tzinfo is None:
            received = received.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        received = datetime.now(timezone.utc)

    return IncomingEmail(
        message_id=message_id,
        graph_id=message_id,  # no IMAP, usamos o Message-ID para manter a thread ao responder
        conversation_id=conversation,
        from_email=address,
        from_name=name,
        reply_to=reply_to,
        to=to,
        cc=cc,
        return_path=str(msg.get("Return-Path") or "").strip("<> "),
        subject=str(msg.get("Subject") or ""),
        body=clean_body(content),
        received_at=received,
        headers={k.lower(): str(v) for k, v in msg.items()},
    )
