"""Rotas de desenvolvimento/demonstração: simulam e-mails sem precisar do Outlook/Gmail."""
from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database import repository as repo
from app.database.connection import SessionLocal
from app.customers.service import load_customers
from app.deps import get_processor
from app.email.models import IncomingEmail
from app.email.sender import ConsoleMailGateway

router = APIRouter(prefix="/dev", tags=["dev"])


class SimulatedEmail(BaseModel):
    from_email: str
    from_name: str = ""
    subject: str = ""
    body: str = ""
    reply_to: list[str] = Field(default_factory=list)
    message_id: str | None = None
    conversation_id: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)


@router.post("/simulate-email")
def simulate_email(payload: SimulatedEmail) -> dict:
    processor = get_processor()
    incoming = IncomingEmail(
        message_id=payload.message_id or f"<sim-{uuid4()}@nova.local>",
        conversation_id=payload.conversation_id or "",
        from_email=payload.from_email,
        from_name=payload.from_name,
        subject=payload.subject,
        body=payload.body,
        reply_to=payload.reply_to,
        headers=payload.headers,
    )
    status = processor.process(incoming)
    return {"message_id": incoming.message_id, "conversation_id": incoming.conversation_id, "status": status}


@router.get("/outbox")
def outbox() -> list[dict]:
    mail = get_processor().mail
    if not isinstance(mail, ConsoleMailGateway):
        raise HTTPException(404, "Outbox só existe no MAIL_MODE=console")
    return mail.outbox


@router.get("/emails")
def emails() -> list[dict]:
    with SessionLocal() as db:
        return [
            {"id": r.id, "from": r.from_email, "subject": r.subject, "status": r.status,
             "cnpj_cpf": r.cnpj_cpf, "conversation_id": r.conversation_id}
            for r in repo.list_recent_emails(db)
        ]


@router.get("/customers")
def customers() -> dict:
    """Lista os clientes lidos agora mesmo do arquivo data/clientes.txt."""
    return load_customers()


@router.get("/pre-atendimentos")
def pre_atendimentos() -> list[dict]:
    """Pré-atendimentos montados para cada atendimento validado (o que iria para o ERP)."""
    with SessionLocal() as db:
        return [
            {
                "id": p.id, "email_id": p.email_id,
                "cliente": p.cliente_nome, "cliente_documento": p.cliente_documento,
                "contato_nome": p.contato_nome, "contato_email": p.contato_email,
                "tipo_atendimento": p.tipo_atendimento, "canal": p.canal,
                "tipo_acesso": p.tipo_acesso, "observacoes": p.observacoes,
                "created_at": p.created_at.isoformat(),
            }
            for p in repo.list_pre_atendimentos(db)
        ]


@router.get("/links")
def links() -> list[dict]:
    """Vínculos contato (e-mail/domínio) <-> CNPJ/CPF que a NOVA já conhece."""
    with SessionLocal() as db:
        nomes = load_customers()
        return [
            {"tipo": link.kind, "valor": link.value, "documento": link.document,
             "cliente": nomes.get(link.document, "(fora da base)"), "origem": link.source,
             "criado_em": link.created_at.isoformat()}
            for link in repo.list_links(db)
        ]
