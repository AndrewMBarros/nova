from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class EmailRecord(Base):
    """Memória da NOVA: um registro por e-mail recebido."""

    __tablename__ = "emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    graph_id: Mapped[Optional[str]] = mapped_column(String(512))
    message_id: Mapped[str] = mapped_column(String(998), unique=True, index=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(String(998), index=True)
    references_raw: Mapped[str] = mapped_column(Text, default="")  # cabeçalho References recebido, para a resposta manter a thread inteira
    from_email: Mapped[str] = mapped_column(String(320))
    from_name: Mapped[Optional[str]] = mapped_column(String(300))
    cc_raw: Mapped[str] = mapped_column(Text, default="")  # destinatários em cópia (Cc), separados por vírgula
    reply_address: Mapped[Optional[str]] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(998), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(40), index=True)
    cnpj_cpf: Mapped[Optional[str]] = mapped_column(String(20))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class ProcessingEvent(Base):
    __tablename__ = "processing_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("emails.id"), index=True)
    event: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ContactLink(Base):
    """Vínculo entre um contato (e-mail exato ou domínio) e o CNPJ/CPF de um cliente.

    É o que permite à NOVA reconhecer quem escreve SEM pedir o CNPJ de novo:
    - kind=EMAIL:  value = endereço completo (lucas@alpha.com)
    - kind=DOMAIN: value = domínio sem "@" (alpha.com) -> vale para todos os funcionários
    O vínculo é criado automaticamente quando um contato é validado pelo CNPJ/CPF
    (source=AUTO) ou à mão, pelo `python -m app.manage_links` (source=MANUAL)."""

    __tablename__ = "contact_links"
    __table_args__ = (UniqueConstraint("kind", "value", "document", name="uq_contact_link"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(10), index=True)        # EMAIL | DOMAIN
    value: Mapped[str] = mapped_column(String(320), index=True)      # e-mail ou domínio, minúsculo
    document: Mapped[str] = mapped_column(String(20), index=True)    # CNPJ/CPF normalizado
    source: Mapped[str] = mapped_column(String(10), default="AUTO")  # AUTO | MANUAL
    first_email_id: Mapped[Optional[int]] = mapped_column(ForeignKey("emails.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PreAtendimento(Base):
    """O que a NOVA monta sozinha para um atendimento: os campos de abertura de chamado.
    Na integração com um ERP, estes campos são enviados a ele (ver README)."""

    __tablename__ = "pre_atendimentos"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("emails.id"), unique=True, index=True)
    cliente_documento: Mapped[str] = mapped_column(String(20))
    cliente_nome: Mapped[str] = mapped_column(String(300))
    contato_nome: Mapped[str] = mapped_column(String(300), default="")
    contato_email: Mapped[str] = mapped_column(String(320))
    tipo_atendimento: Mapped[str] = mapped_column(String(100), default="Suporte Técnico")
    canal: Mapped[str] = mapped_column(String(50), default="E-mail")
    tipo_acesso: Mapped[str] = mapped_column(String(50), default="Remoto")
    observacoes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AppState(Base):
    """Estado da NOVA (ex.: corte inicial e cursor de leitura)."""

    __tablename__ = "app_state"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
