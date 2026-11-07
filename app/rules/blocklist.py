"""Lista de remetentes/domínios bloqueados, mantida num arquivo texto
(data/bloqueados.txt) - separada do BLOCKED_SENDERS do .env, que continua
funcionando para um bloqueio rápido e pontual. As duas listas são somadas.

O noreply (noreply@, no-reply@, mailer-daemon@...) continua sendo uma regra
fixa no código (app/rules/engine.py) - não precisa cadastrar aqui.
"""
from __future__ import annotations

from pathlib import Path

from app.config import settings


def _blocklist_path() -> Path:
    return Path(settings.blocked_senders_file)


def load_blocked_senders() -> list[str]:
    path = _blocklist_path()
    if not path.exists():
        return []
    out = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip().lower()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out
