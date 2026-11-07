"""Consulta de clientes cadastrados em um arquivo texto (base simulada).

O arquivo (padrão: data/clientes.txt) é a "base de clientes" provisória, no
formato `documento;nome` por linha, com uma 3ª coluna OPCIONAL de contatos
conhecidos: `documento;nome;@alpha.com,lucas@outro.com` (um domínio inteiro
com "@", e/ou e-mails avulsos). Esses contatos se somam aos vínculos que a
NOVA aprende sozinha (tabela contact_links). O conteúdo fica em cache em memória,
invalidado pela data de modificação do arquivo (mtime) — editar e salvar
ainda vale no teste seguinte, sem reiniciar nada, mas sem reler e reparsear o
arquivo inteiro a cada CNPJ consultado (um e-mail com 2 documentos, por
exemplo, consulta a base várias vezes no mesmo processamento).

Na integração com um ERP, `find_customer()` passa a consultar o ERP de verdade.
Esta é a ÚNICA função que muda quando isso acontecer.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.documents.validator import normalize


@dataclass
class Customer:
    document: str
    name: str


def _customers_path() -> Path:
    return Path(settings.customers_file)


_cache: dict[str, tuple[float, dict[str, str], dict[str, list[str]], dict[str, list[str]]]] = {}


def _load() -> tuple[dict[str, str], dict[str, list[str]], dict[str, list[str]]]:
    """Lê o arquivo (com cache por mtime). Devolve ({documento: nome}, {documento: [contatos]},
    {documento: [apelidos]}). Os apelidos são a 4ª coluna opcional (separados por vírgula) e
    servem só para reconhecer o cliente pelo NOME citado no e-mail (ver customers/names.py)."""
    path = _customers_path()
    key = str(path)
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        _cache.pop(key, None)
        return {}, {}, {}

    cached = _cache.get(key)
    if cached and cached[0] == mtime:
        return cached[1], cached[2], cached[3]

    customers: dict[str, str] = {}
    contacts: dict[str, list[str]] = {}
    aliases: dict[str, list[str]] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ";" not in line:
            continue
        parts = [p.strip() for p in line.split(";")]
        document = normalize(parts[0])
        name = parts[1] if len(parts) > 1 else ""
        if document and name:
            customers[document] = name
            if len(parts) > 2 and parts[2]:
                contacts[document] = [c.strip().lower() for c in parts[2].split(",") if c.strip()]
            if len(parts) > 3 and parts[3]:
                aliases[document] = [a.strip() for a in parts[3].split(",") if a.strip()]
    _cache[key] = (mtime, customers, contacts, aliases)
    return customers, contacts, aliases


def load_customers() -> dict[str, str]:
    """{documento_normalizado: nome}. Linhas em branco ou começando com # são
    ignoradas. Se o arquivo não existir, devolve vazio (a NOVA passa a tratar
    todo mundo como "não cadastrado", sem quebrar)."""
    return _load()[0]


def load_file_contacts() -> dict[str, list[str]]:
    """{documento_normalizado: ["@alpha.com", "lucas@x.com", ...]} — a 3ª coluna do arquivo."""
    return _load()[1]


def load_aliases() -> dict[str, list[str]]:
    """{documento_normalizado: [\"Omega Auto\", ...]} — a 4ª coluna do arquivo."""
    return _load()[2]


def find_customer(document: str) -> Customer | None:
    name = load_customers().get(normalize(document))
    return Customer(document=document, name=name) if name else None
