"""Extração, normalização e validação de CNPJ e CPF.

Suporta o CNPJ alfanumérico (em vigor a partir de julho/2026): as 12
primeiras posições podem ter letras e os 2 últimos caracteres são sempre
dígitos verificadores.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_SEP = re.compile(r"[^0-9A-Za-z]")
_W1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
_W2 = [6] + _W1

_CNPJ_RE = re.compile(
    r"(?<![A-Za-z0-9])[A-Za-z0-9]{2}\.?[A-Za-z0-9]{3}\.?[A-Za-z0-9]{3}/?[A-Za-z0-9]{4}-?[0-9]{2}(?![A-Za-z0-9])"
)
_CPF_RE = re.compile(r"(?<![\w./-])\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\w)")
_CONTEXT_RE = re.compile(r"cnpj|cpf|documento|\bdoc\b", re.I)


@dataclass(frozen=True)
class Document:
    kind: str    # "CNPJ" ou "CPF"
    number: str  # normalizado (só caracteres, sem pontuação)

    @property
    def formatted(self) -> str:
        n = self.number
        if self.kind == "CNPJ":
            return f"{n[:2]}.{n[2:5]}.{n[5:8]}/{n[8:12]}-{n[12:]}"
        return f"{n[:3]}.{n[3:6]}.{n[6:9]}-{n[9:]}"


def normalize(value: str) -> str:
    return _SEP.sub("", value or "").upper()


def _cnpj_digit(base: str, weights: list[int]) -> str:
    total = sum((ord(c) - 48) * w for c, w in zip(base, weights))
    r = total % 11
    return "0" if r < 2 else str(11 - r)


def is_valid_cnpj(value: str) -> bool:
    n = normalize(value)
    if not re.fullmatch(r"[0-9A-Z]{12}[0-9]{2}", n) or len(set(n)) == 1:
        return False
    d1 = _cnpj_digit(n[:12], _W1)
    d2 = _cnpj_digit(n[:12] + d1, _W2)
    return n[12:] == d1 + d2


def _cpf_digit(base: str) -> str:
    total = sum(int(d) * w for d, w in zip(base, range(len(base) + 1, 1, -1)))
    r = (total * 10) % 11
    return "0" if r == 10 else str(r)


def is_valid_cpf(value: str) -> bool:
    n = normalize(value)
    if not re.fullmatch(r"\d{11}", n) or len(set(n)) == 1:
        return False
    d1 = _cpf_digit(n[:9])
    d2 = _cpf_digit(n[:9] + d1)
    return n[9:] == d1 + d2


def _unformatted(raw: str) -> bool:
    return not re.search(r"[./-]", raw)


def _has_context(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 40):start] + " " + text[end:end + 40]
    return bool(_CONTEXT_RE.search(window))


def extract_documents(text: str) -> list[Document]:
    """Devolve os CNPJ/CPF válidos encontrados no texto, na ordem em que aparecem."""
    text = text or ""
    found: list[tuple[int, Document]] = []
    masked = list(text)

    for m in _CNPJ_RE.finditer(text):
        raw = m.group()
        if not is_valid_cnpj(raw):
            continue
        found.append((m.start(), Document("CNPJ", normalize(raw))))
        for i in range(m.start(), m.end()):
            masked[i] = " "

    masked_text = "".join(masked)
    short_message = len(text.strip()) <= 40
    for m in _CPF_RE.finditer(masked_text):
        raw = m.group()
        if not is_valid_cpf(raw):
            continue
        # CPF só com dígitos parece número de telefone: exige contexto
        if _unformatted(raw) and not (short_message or _has_context(text, m.start(), m.end())):
            continue
        found.append((m.start(), Document("CPF", normalize(raw))))

    found.sort(key=lambda item: item[0])
    unique: list[Document] = []
    for _, doc in found:
        if doc not in unique:
            unique.append(doc)
    return unique


# Candidato "solto": algo que parece um CNPJ/CPF, mas com a QUANTIDADE de caracteres errada
# (faltou ou sobrou dígito). O formato exato (14 / 11) é tratado pelos regex acima.
_LOOSE_RE = re.compile(r"(?<![A-Za-z0-9@])[A-Za-z0-9][A-Za-z0-9./-]{7,22}[A-Za-z0-9](?![A-Za-z0-9@])")
_CNPJ_TYPO_LENGTHS = {12, 13, 15, 16}
_CPF_TYPO_LENGTHS = {9, 10}


def find_invalid_document(text: str) -> str | None:
    """Devolve o 1º trecho do texto que PARECE um CNPJ/CPF mas está incorreto (dígito verificador
    que não confere, ou quantidade errada de dígitos), exatamente como o cliente digitou.
    None se nada parece documento. Mesma cautela de sempre para números soltos (telefone,
    protocolo): só conta se a mensagem for curta ou a palavra CNPJ/CPF/documento estiver perto."""
    text = text or ""
    short_message = len(text.strip()) <= 40
    found: list[tuple[int, str]] = []

    for m in _CNPJ_RE.finditer(text):
        if not is_valid_cnpj(m.group()):
            found.append((m.start(), m.group()))
    masked = _CNPJ_RE.sub(lambda m: " " * len(m.group()), text)

    for m in _CPF_RE.finditer(masked):
        if is_valid_cpf(m.group()):
            continue
        if _unformatted(m.group()) and not (short_message or _has_context(text, m.start(), m.end())):
            continue
        found.append((m.start(), m.group()))
    masked = _CPF_RE.sub(lambda m: " " * len(m.group()), masked)

    for m in _LOOSE_RE.finditer(masked):
        raw = m.group()
        n = normalize(raw)
        digits = sum(c.isdigit() for c in n)
        if digits < len(n) - 4 or digits < 8:
            continue
        if len(n) not in _CNPJ_TYPO_LENGTHS | _CPF_TYPO_LENGTHS:
            continue
        # com pontuação de documento ou com contexto; senão só se a mensagem for curta
        # CPF com dígito faltando só conta com a palavra CNPJ/CPF/documento por perto (senão é telefone)
        if not (_has_context(text, m.start(), m.end()) or (short_message and len(n) in _CNPJ_TYPO_LENGTHS)):
            continue
        if re.fullmatch(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}", raw):  # data
            continue
        found.append((m.start(), raw))

    if not found:
        return None
    return min(found)[1]


def looks_like_document(text: str) -> bool:
    """True se existe algo com formato de CNPJ/CPF no texto, mesmo incorreto (dígito errado ou
    faltando/sobrando). Separa "não mandou nada" de "mandou um número, mas está incorreto"."""
    return find_invalid_document(text) is not None


def describe_invalid(raw: str) -> str:
    """Por que o número digitado está incorreto, em linguagem simples."""
    n = normalize(raw)
    if len(n) in (11, 14):
        return "os dígitos verificadores não conferem"
    return f"tem {len(n)} caracteres (o CNPJ tem 14 e o CPF tem 11)"


def display_document(number: str) -> str:
    """CNPJ formatado; CPF com os primeiros e últimos dígitos ocultos."""
    n = normalize(number)
    if len(n) == 11 and n.isdigit():
        return f"***.{n[3:6]}.{n[6:9]}-**"
    if len(n) == 14:
        return Document("CNPJ", n).formatted
    return raw_or_dash(number)


def raw_or_dash(value: str) -> str:
    return (value or "").strip() or "-"
