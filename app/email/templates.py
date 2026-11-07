"""Textos das mensagens da NOVA."""
from __future__ import annotations

from app.config import settings

# Nome da empresa que aparece nas mensagens: COMPANY_NAME no .env.
COMPANY = settings.company_name

SIGNATURE = f"Atenciosamente,\n\nNOVA\nSecretaria Virtual\n{COMPANY}"

# Só nas mensagens para o CLIENTE (não nos avisos internos à equipe, que já
# sabem que é automático). Deixa claro que não é uma pessoa do outro lado, sem
# soar como "não responda este e-mail" — a NOVA precisa que ele responda.
AUTOMATED_NOTE = (
    "\n\n— Esta é uma mensagem automática enviada pela NOVA, assistente "
    f"virtual de atendimento da {COMPANY}. Pode responder este e-mail "
    "normalmente. —"
)


def re_subject(subject: str) -> str:
    s = (subject or "").strip() or "Sua solicitação"
    return s if s.lower().startswith(("re:", "res:")) else f"Re: {s}"


def request_document() -> str:
    return (
        "Olá,\n\n"
        "Recebemos sua solicitação e, para darmos continuidade ao atendimento, "
        "precisamos identificar o cadastro da empresa.\n\n"
        "Por favor, responda este e-mail informando o CNPJ ou CPF vinculado ao "
        f"seu contrato com a {COMPANY}.\n\n"
        "Assim que recebermos essa informação, daremos prosseguimento à solicitação."
        + AUTOMATED_NOTE + "\n\n"
        + SIGNATURE
    )


def document_invalid(informado: str = "", motivo: str = "") -> str:
    """Cliente mandou algo no formato de CNPJ/CPF, mas o número está incorreto (dígito verificador
    que não confere, ou dígito faltando/sobrando). Diz o que recebeu e pede o número certo."""
    quem = f" ({informado})" if informado else ""
    por_que = f": {motivo}" if motivo else ""
    return (
        "Olá,\n\n"
        f"O CNPJ/CPF informado{quem} não parece estar correto{por_que}. "
        "Confira os números digitados.\n\n"
        "Por favor, responda este e-mail informando novamente o CNPJ ou CPF vinculado "
        f"ao seu contrato com a {COMPANY}."
        + AUTOMATED_NOTE + "\n\n"
        + SIGNATURE
    )


def document_limit(informado: str = "") -> str:
    """Última mensagem ao cliente quando as tentativas acabaram: avisa que a equipe vai conferir."""
    quem = f" ({informado})" if informado else ""
    return (
        "Olá,\n\n"
        f"Não conseguimos validar o CNPJ/CPF informado{quem}.\n\n"
        "Encaminhamos sua solicitação para nossa equipe, que entrará em contato "
        "para confirmar os dados do seu cadastro."
        + AUTOMATED_NOTE + "\n\n"
        + SIGNATURE
    )


def customer_validated(nome: str = "", documento: str = "", via_link: bool = False) -> str:
    """Cliente encontrado na base. Diz QUAL cadastro foi reconhecido (o cliente vê que deu certo).
    Com um ERP integrado, esta mensagem deve ser enviada só depois de o chamado ser aberto."""
    if nome and via_link:
        ident = f": {nome}"
    elif nome and documento:
        ident = f": {nome} ({documento})"
    elif nome:
        ident = f": {nome}"
    else:
        ident = ""
    return (
        "Olá,\n\n"
        f"Confirmamos o seu cadastro{ident}. Estamos providenciando o atendimento à sua "
        "solicitação e em breve um de nossos colaboradores dará continuidade a ela."
        + AUTOMATED_NOTE + "\n\n"
        + SIGNATURE
    )


def customer_identified_by_name(nome: str) -> str:
    """Cliente reconhecido só pelo NOME que ele mesmo citou (sem CNPJ/CPF). Só repete o nome
    do cadastro, que por construção já está no texto do cliente; não revela CNPJ nem outros dados."""
    return (
        "Olá,\n\n"
        f"Identificamos o seu cadastro pelo nome da empresa informado: {nome}. Estamos providenciando "
        "o atendimento à sua solicitação e em breve um de nossos colaboradores dará continuidade a ela, "
        "confirmando os seus dados."
        + AUTOMATED_NOTE + "\n\n"
        + SIGNATURE
    )


def customer_not_found(informado: str = "") -> str:
    """CNPJ/CPF com formato válido, mas fora da base. Não confirma atendimento - a equipe valida antes."""
    quem = f" {informado}" if informado else ""
    return (
        "Olá,\n\n"
        f"O CNPJ/CPF{quem} informado é válido, mas não localizamos um cadastro ativo com ele.\n\n"
        "Encaminhamos sua solicitação para nossa equipe, que entrará em contato "
        "para confirmar os dados do seu contrato."
        + AUTOMATED_NOTE + "\n\n"
        + SIGNATURE
    )


def _preview(text: str, limit: int = 600) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "..."


def team_customer_not_found(*, document: str, sender: str, subject: str, body: str) -> tuple[str, str]:
    return (
        "NOVA - Cliente não localizado na base",
        "Olá, equipe.\n\n"
        "A NOVA recebeu uma solicitação e não localizou o cliente informado.\n\n"
        f"CNPJ/CPF informado: {document}\n"
        f"E-mail: {sender}\n"
        f"Assunto: {subject}\n\n"
        f"Mensagem do cliente:\n{_preview(body)}\n\n"
        "Encaminhado para validação manual.\n\n" + SIGNATURE,
    )


def team_review(*, reason: str, sender: str, subject: str, body: str) -> tuple[str, str]:
    return (
        "NOVA - Solicitação precisa de análise humana",
        "Olá, equipe.\n\n"
        f"Motivo: {reason}\n\n"
        f"E-mail: {sender}\n"
        f"Assunto: {subject}\n\n"
        f"Mensagem do cliente:\n{_preview(body)}\n\n" + SIGNATURE,
    )
