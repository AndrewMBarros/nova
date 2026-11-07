"""Identificação do cliente pelo NOME que ele cita no e-mail.

Quando o remetente não é reconhecido por e-mail/domínio e não informa CNPJ/CPF,
a NOVA procura, na assinatura e nas frases de apresentação, o nome de algum
cliente cadastrado ("Omega Comercial Automotivo" -> cliente "Omega").

Regras de segurança (nome não prova identidade como o CNPJ prova):
  * a direção do teste é "o nome do CADASTRO aparece inteiro no texto" — nunca o
    contrário. Assim "Omega" casa com "Omega Comercial Automotivo", mas "Omega Pecas &
    Acessorios" só casa se o texto citar "Pecas" e "Acessorios";
  * vence o nome mais específico (mais palavras): "Omega Vila Nova" ganha de "Omega";
  * empate entre clientes diferentes = AMBÍGUO: a NOVA não chuta e pede o CNPJ/CPF;
  * nomes só com palavras genéricas ("Comercial Automotivo Ltda") nunca casam.

Módulo puro (só biblioteca padrão): não acessa banco nem arquivo.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Sufixos societários, ignorados no FIM do nome do cadastro.
LEGAL_SUFFIXES = frozenset({"ltda", "me", "epp", "eireli", "sa", "s", "a", "ss", "mei", "cia"})

# Palavras que sozinhas não identificam ninguém. Um nome do cadastro precisa ter
# pelo menos UMA palavra fora desta lista (e com 3+ letras) para poder casar.
GENERIC_WORDS = frozenset({
    "de", "da", "do", "das", "dos", "e", "em", "a", "o", "para", "com",
    "empresa", "cliente", "grupo", "comercio", "comercial", "servicos", "servico",
    "industria", "industrial", "distribuidora", "transportes", "transporte",
    "tecnologia", "solucoes", "sistemas", "automotivo", "automotiva", "automoveis",
    "brasil", "brasileira", "nacional", "filial", "matriz", "unidade", "loja",
    "clinica", "construtora", "engenharia", "consultoria", "assessoria", "associacao",
    "representacoes", "importacao", "exportacao", "participacoes", "holding",
})

# Conectores ignorados na comparação ("Pecas & Acessorios" = "Pecas e Acessorios"; "Padaria da Esquina" = "Padaria Esquina").
CONNECTORS = frozenset({"e", "de", "da", "do", "das", "dos"})

# Frases de apresentação ("sou da X", "aqui é da X", "da empresa X") — além da assinatura.
_INTRO = re.compile(
    r"\b(sou|somos|aqui\s+[eé]|falo|falamos|escrevo|entro\s+em\s+contato|empresa|cliente|filial|unidade)\b",
    re.I,
)
_SIGNATURE_LINES = 6


def tokens(text: str) -> list[str]:
    """Minúsculas, sem acento, só letras/números ('Pecas & Acessorios' -> ['pecas', 'acessorios'])."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return re.findall(r"[a-z0-9]+", text)


def core_tokens(name: str) -> list[str]:
    """Palavras que identificam o cadastro: sem '(...)' e sem sufixo societário no fim."""
    toks = [t for t in tokens(re.sub(r"\([^)]*\)", " ", name or "")) if t not in CONNECTORS]
    while toks and toks[-1] in LEGAL_SUFFIXES:
        toks.pop()
    return toks


def is_usable(toks: list[str]) -> bool:
    """Tem alguma palavra distintiva? ('omega' sim; 'comercial automotivo' não)."""
    return any(len(t) >= 3 and t not in GENERIC_WORDS for t in toks)


def _contains(haystack: list[str], needle: list[str]) -> bool:
    n = len(needle)
    return n > 0 and any(haystack[i:i + n] == needle for i in range(len(haystack) - n + 1))


def candidate_lines(subject: str = "", body: str = "", from_name: str = "") -> list[str]:
    """Trechos onde um cliente costuma se identificar: nome do remetente, assunto,
    assinatura (últimas linhas) e frases de apresentação. Cada linha é testada à parte —
    palavras de linhas diferentes nunca se juntam para formar um nome."""
    lines: list[str] = []
    if from_name:
        lines.append(from_name)
    if subject:
        lines.append(subject)
    body_lines = [ln.strip() for ln in (body or "").replace("\r", "\n").split("\n") if ln.strip()]
    lines.extend(body_lines[-_SIGNATURE_LINES:])
    lines.extend(ln for ln in body_lines[:-_SIGNATURE_LINES] if _INTRO.search(ln))
    return lines


@dataclass
class NameMatch:
    document: str = ""                 # preenchido só quando há UM cliente inequívoco
    name: str = ""                     # nome no cadastro
    matched_as: str = ""               # a variante (nome ou apelido) que casou
    ambiguous: list[str] = field(default_factory=list)   # documentos empatados

    @property
    def found(self) -> bool:
        return bool(self.document)


def match_customer(customers: dict[str, str], lines: list[str],
                   aliases: dict[str, list[str]] | None = None) -> NameMatch:
    """`customers` = {documento: nome}; `aliases` = {documento: [apelidos]} (opcional)."""
    aliases = aliases or {}
    haystacks = [[t for t in tokens(ln) if t not in CONNECTORS] for ln in lines if ln]
    best_score = 0
    winners: dict[str, tuple[str, str]] = {}   # documento -> (nome no cadastro, variante que casou)

    for document, name in customers.items():
        for variant in [name, *aliases.get(document, [])]:
            toks = core_tokens(variant)
            if not is_usable(toks) or not any(_contains(h, toks) for h in haystacks):
                continue
            score = len(toks)
            if score > best_score:
                best_score, winners = score, {}
            if score == best_score:
                winners.setdefault(document, (name, variant))

    if not winners:
        return NameMatch()
    if len(winners) > 1:
        return NameMatch(ambiguous=sorted(winners))
    document, (name, variant) = next(iter(winners.items()))
    return NameMatch(document=document, name=name, matched_as=variant)
