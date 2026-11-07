"""Vínculo contato <-> cliente.

Ideia: quem já foi validado pelo CNPJ/CPF uma vez não precisa informá-lo de novo.
A NOVA guarda (tabela `contact_links`) o e-mail exato de quem foi validado e,
como uma empresa tem vários funcionários, também o DOMÍNIO do e-mail
(lucas@alpha.com e pedro@alpha.com -> alpha.com -> Empresa Alpha).

Ordem de busca ao reconhecer um remetente:
  1. e-mail exato   (mais específico: vale até para quem usa Gmail/Outlook);
  2. domínio        (só domínios corporativos — nunca gmail.com, outlook.com etc.).
Em cada nível só conta cliente que AINDA existe na base (se o cliente foi
removido do clientes.txt, o vínculo fica "velho" e é ignorado). Se o mesmo
contato/domínio aponta para mais de um cliente, é AMBÍGUO: a NOVA não chuta e
pede o CNPJ/CPF, como antes.

Fontes dos vínculos: o que a NOVA aprende (AUTO), o que for cadastrado com
`python -m app.manage_links` (MANUAL) e a 3ª coluna opcional do clientes.txt.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.customers.service import Customer, find_customer, load_file_contacts
from app.database import repository as repo
from app.documents.validator import normalize
from app.rules.engine import is_valid_address

EMAIL = "EMAIL"
DOMAIN = "DOMAIN"

# Provedores públicos: milhares de empresas diferentes usam o mesmo domínio, então
# vincular "@gmail.com" a um cliente faria TODO usuário de Gmail virar esse cliente.
SHARED_DOMAINS = frozenset({
    "gmail.com", "googlemail.com", "hotmail.com", "hotmail.com.br", "outlook.com", "outlook.com.br",
    "live.com", "msn.com", "yahoo.com", "yahoo.com.br", "ymail.com", "rocketmail.com", "icloud.com",
    "me.com", "mac.com", "aol.com", "proton.me", "protonmail.com", "pm.me", "zoho.com", "gmx.com",
    "mail.com", "bol.com.br", "uol.com.br", "terra.com.br", "ig.com.br", "globo.com", "globomail.com",
    "r7.com", "oi.com.br", "zipmail.com.br", "click21.com.br",
})


def split_address(address: str) -> tuple[str, str]:
    address = (address or "").strip().lower()
    local, _, domain = address.rpartition("@")
    return local, domain


def is_shared_domain(domain: str, extra: list[str] | tuple[str, ...] = ()) -> bool:
    domain = (domain or "").strip().lower().lstrip("@")
    return domain in SHARED_DOMAINS or domain in set(extra)


@dataclass
class ContactMatch:
    customer: Customer | None = None   # preenchido só quando há UM cliente inequívoco
    via: str = ""                      # "email" | "domain"
    matched: str = ""                  # o e-mail ou domínio que bateu
    ambiguous: list[str] = field(default_factory=list)  # documentos, quando há mais de um
    stale: int = 0                     # vínculos ignorados porque o cliente não está mais na base


def _documents_for(db: Session, kind: str, value: str, *, allow_auto_domain: bool = False) -> list[str]:
    links = repo.get_links(db, kind, value)
    # Domínios aprendidos automaticamente (AUTO) só valem com LINK_DOMAIN_AUTO ligado: se a
    # opção for desligada, os que já foram gravados deixam de liberar novos endereços sem CNPJ.
    if kind == DOMAIN and not allow_auto_domain:
        links = [link for link in links if link.source != "AUTO"]
    docs: list[str] = [lk.document for lk in links]
    entry = value if kind == EMAIL else f"@{value}"
    for document, entries in load_file_contacts().items():
        if entry in entries and document not in docs:
            docs.append(document)
    return docs


def resolve(db: Session, address: str, shared_extra: list[str] | tuple[str, ...] = (), *,
            allow_auto_domain: bool = False) -> ContactMatch:
    """Descobre de qual cliente é este remetente, sem precisar do CNPJ no e-mail."""
    address = (address or "").strip().lower()
    result = ContactMatch()
    if not is_valid_address(address):
        return result
    _, domain = split_address(address)

    levels = [(EMAIL, address, "email")]
    if not is_shared_domain(domain, shared_extra):
        levels.append((DOMAIN, domain, "domain"))

    for kind, value, via in levels:
        live: list[Customer] = []
        for document in _documents_for(db, kind, value, allow_auto_domain=allow_auto_domain):
            customer = find_customer(document)
            if customer is None:
                result.stale += 1
            else:
                live.append(customer)
        if len(live) == 1:
            result.customer, result.via, result.matched = live[0], via, value
            return result
        if len(live) > 1:
            result.ambiguous = [c.document for c in live]
            result.via, result.matched = via, value
            return result
    return result


def learn(db: Session, address: str, document: str, *, link_domain: bool,
          shared_extra: list[str] | tuple[str, ...] = (), email_id: int | None = None) -> list[tuple[str, str]]:
    """Grava o vínculo de um contato recém-validado. Devolve [(descrição, valor)] do que foi criado/negado.

    - E-mail exato: sempre.
    - Domínio: só se `link_domain`, se não for provedor público e se o domínio ainda não
      pertencer a OUTRO cliente (o primeiro vínculo vale; um e-mail avulso citando o CNPJ
      de outro cliente não "rouba" nem torna ambíguo o domínio inteiro)."""
    address = (address or "").strip().lower()
    document = normalize(document)
    if not is_valid_address(address) or not document:
        return []
    out: list[tuple[str, str]] = []
    if repo.add_link(db, kind=EMAIL, value=address, document=document, email_id=email_id):
        out.append(("EMAIL_LINKED", address))
    if link_domain:
        _, domain = split_address(address)
        if is_shared_domain(domain, shared_extra):
            return out
        others = [d for d in _documents_for(db, DOMAIN, domain, allow_auto_domain=True)
                  if d != document and find_customer(d)]
        if others:
            out.append(("DOMAIN_LINK_CONFLICT", domain))
        elif repo.add_link(db, kind=DOMAIN, value=domain, document=document, email_id=email_id):
            out.append(("DOMAIN_LINKED", domain))
    return out
