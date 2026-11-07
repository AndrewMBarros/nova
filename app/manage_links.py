"""Utilitário para os vínculos contato <-> cliente (a NOVA também aprende sozinha: ver app/customers/contacts.py).

Uso:
  python -m app.manage_links listar
  python -m app.manage_links adicionar "12.345.678/0001-95" "@alpha.com"          # domínio inteiro
  python -m app.manage_links adicionar "12.345.678/0001-95" "lucas@alpha.com"    # um e-mail só
  python -m app.manage_links remover "@alpha.com"                                 # todos os clientes desse valor
  python -m app.manage_links remover "lucas@alpha.com" "12.345.678/0001-95"      # só o vínculo com esse cliente
"""
from __future__ import annotations

import sys

from app.config import settings
from app.customers import contacts
from app.customers.service import find_customer, load_customers
from app.database import repository as repo
from app.database.connection import SessionLocal, init_db
from app.documents.validator import normalize


def listar() -> None:
    with SessionLocal() as db:
        rows = repo.list_links(db)
    if not rows:
        print("Nenhum vínculo ainda. (A NOVA cria sozinha quando um contato é validado pelo CNPJ/CPF.)")
        return
    nomes = load_customers()
    for link in rows:
        valor = f"@{link.value}" if link.kind == contacts.DOMAIN else link.value
        print(f"{valor:35} -> {nomes.get(link.document, '(cliente fora da base)')} [{link.document}] ({link.source})")
    print(f"\nTotal: {len(rows)} vínculo(s).")


def adicionar(document: str, value: str) -> None:
    document = normalize(document)
    value = value.strip().lower()
    if find_customer(document) is None:
        print(f"Aviso: {document} não está no data/clientes.txt; o vínculo só vale quando o cliente existir lá.")
    if value.startswith("@"):
        kind, value = contacts.DOMAIN, value[1:]
        if contacts.is_shared_domain(value, settings.shared_domain_list):
            print(f"Recusado: {value} é um provedor público (Gmail, Outlook...). Vincule o e-mail completo.")
            return
    else:
        kind = contacts.EMAIL
        if "@" not in value:
            print("Informe um e-mail completo (lucas@alpha.com) ou um domínio com @ (@alpha.com).")
            return
    init_db()
    with SessionLocal() as db:
        created = repo.add_link(db, kind=kind, value=value, document=document, source="MANUAL")
    print("Vínculo criado." if created else "Esse vínculo já existia.")


def remover(value: str, document: str | None = None) -> None:
    init_db()
    with SessionLocal() as db:
        n = repo.delete_links(db, value.strip().lower().lstrip("@"), normalize(document) if document else None)
    print(f"{n} vínculo(s) removido(s).")


def main() -> None:
    a = sys.argv[1:]
    if a[:1] == ["listar"]:
        init_db()
        listar()
    elif a[:1] == ["adicionar"] and len(a) == 3:
        adicionar(a[1], a[2])
    elif a[:1] == ["remover"] and len(a) in (2, 3):
        remover(*a[1:])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
