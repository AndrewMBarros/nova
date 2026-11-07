"""Regra de grupo: e-mails vindos de, ou com cópia (Cc) para, certas pessoas vão DIRETO
para um cliente/grupo, sem pedir CNPJ/CPF.

Exemplo: Carlos trabalha para o Grupo Sigma; a empresa dele, mesmo sendo cliente à parte,
faz parte do grupo. Então qualquer e-mail dele (no De ou no Cc) é cadastrado em "Grupo Sigma".

Arquivo (padrão data/grupos.txt), uma linha por grupo: `documento;endereco1,endereco2,@dominio`.
O documento precisa existir em clientes.txt (senão a regra é ignorada). Cache por mtime.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.customers.service import Customer, find_customer
from app.documents.validator import normalize

_cache: dict[str, tuple[float, list[tuple[str, list[str]]]]] = {}


def _load() -> list[tuple[str, list[str]]]:
    path = Path(settings.group_rules_file)
    key = str(path)
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        _cache.pop(key, None)
        return []
    cached = _cache.get(key)
    if cached and cached[0] == mtime:
        return cached[1]
    rules: list[tuple[str, list[str]]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ";" not in line:
            continue
        doc, _, addrs = line.partition(";")
        document = normalize(doc)
        entries = [a.strip().lower() for a in addrs.split(",") if a.strip()]
        if document and entries:
            rules.append((document, entries))
    _cache[key] = (mtime, rules)
    return rules


@dataclass
class GroupMatch:
    customer: Customer
    matched: str   # endereço que bateu
    where: str     # "De" | "Cc"


def _hit(address: str, entries: list[str]) -> bool:
    address = (address or "").strip().lower()
    if not address:
        return False
    return address in entries or any(e.startswith("@") and address.endswith(e) for e in entries)


def resolve_group(from_email: str, cc: list[str] | tuple[str, ...] = ()) -> GroupMatch | None:
    for document, entries in _load():
        customer = find_customer(document)
        if customer is None:
            continue
        if _hit(from_email, entries):
            return GroupMatch(customer, (from_email or "").strip().lower(), "De")
        for address in cc:
            if _hit(address, entries):
                return GroupMatch(customer, address.strip().lower(), "Cc")
    return None
