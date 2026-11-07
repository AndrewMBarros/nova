"""Regras determinísticas da NOVA (sem IA): noreply, e-mails automáticos, endereço de resposta."""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from app.email.models import IncomingEmail


class Action(str, Enum):
    PROCEED = "PROCEED"
    IGNORE_SELF = "IGNORE_SELF"
    IGNORE_NOREPLY = "IGNORE_NOREPLY"
    IGNORE_AUTOMATED = "IGNORE_AUTOMATED"
    IGNORE_BLOCKED = "IGNORE_BLOCKED"


@dataclass
class PreCheck:
    action: Action
    reply_address: str | None = None
    reason: str = ""


_NOREPLY_RE = re.compile(
    r"no[-_.]?reply|do[-_.]?not[-_.]?reply|n[aã]o[-_.]?responda|n[aã]o[-_.]?responder"
    r"|mailer-daemon|postmaster|bounce",
    re.I,
)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_BULK_PRECEDENCE = {"bulk", "junk", "list", "auto_reply"}


def is_valid_address(address: str) -> bool:
    return bool(_EMAIL_RE.match(address or ""))


def is_noreply(address: str, extra_blocked: list[str] | tuple[str, ...] = ()) -> bool:
    address = (address or "").lower()
    local = address.partition("@")[0]
    if _NOREPLY_RE.search(local):
        return True
    return any(p and p in address for p in extra_blocked)


def automation_reason(headers: dict[str, str]) -> str | None:
    """Detecta e-mails gerados por sistemas (respostas automáticas, listas, bounces)."""
    auto = headers.get("auto-submitted", "").strip().lower()
    if auto and auto != "no":
        return f"Auto-Submitted: {auto}"
    prec = headers.get("precedence", "").strip().lower()
    if prec in _BULK_PRECEDENCE:
        return f"Precedence: {prec}"
    for name in ("list-id", "x-autoreply", "x-autorespond"):
        if name in headers:
            return f"cabeçalho {name}"
    if "multipart/report" in headers.get("content-type", "").lower():
        return "relatório de entrega (bounce)"
    return None


def pre_check(
    email: IncomingEmail,
    *,
    nova_email: str = "",
    extra_blocked: list[str] | tuple[str, ...] = (),
    allow_reply_to_on_noreply: bool = False,
    blocked_subjects: list[str] | tuple[str, ...] = (),
    only_senders: list[str] | tuple[str, ...] = (),
) -> PreCheck:
    """Decide se a NOVA pode processar/responder e para qual endereço."""
    nova = (nova_email or "").lower()
    sender = email.from_email

    if nova and sender == nova:
        return PreCheck(Action.IGNORE_SELF, reason="e-mail enviado pela própria NOVA")

    if only_senders and not any(p in sender for p in only_senders):
        return PreCheck(Action.IGNORE_BLOCKED, reason="remetente fora da lista do piloto (ONLY_SENDERS)")

    reason = automation_reason(email.headers)
    if reason:
        return PreCheck(Action.IGNORE_AUTOMATED, reason=reason)

    subject = (email.subject or "").lower()
    if any(p and p in subject for p in blocked_subjects):
        return PreCheck(Action.IGNORE_BLOCKED, reason="assunto na lista de bloqueio (BLOCKED_SUBJECTS)")

    sender_is_noreply = is_noreply(sender, extra_blocked)
    if sender_is_noreply and not allow_reply_to_on_noreply:
        return PreCheck(Action.IGNORE_NOREPLY, reason=f"remetente noreply: {sender}")

    candidates = list(email.reply_to)
    if not sender_is_noreply:
        candidates.append(sender)

    for addr in candidates:
        if is_valid_address(addr) and not is_noreply(addr, extra_blocked) and addr != nova:
            return PreCheck(Action.PROCEED, reply_address=addr)

    return PreCheck(Action.IGNORE_NOREPLY, reason="nenhum endereço de resposta válido")
