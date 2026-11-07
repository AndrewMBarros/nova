from datetime import datetime
import re

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.timeutil import to_utc
from app.database.models import (
    AppState, ContactLink, EmailRecord, PreAtendimento, ProcessingEvent, utcnow,
)
from app.email.models import IncomingEmail
from app.rules.states import Status


def get_email_by_message_id(db: Session, message_id: str) -> EmailRecord | None:
    return db.scalar(select(EmailRecord).where(EmailRecord.message_id == message_id))


def create_email(db: Session, inc: IncomingEmail) -> EmailRecord:
    rec = EmailRecord(
        message_id=inc.message_id,
        graph_id=inc.graph_id or None,
        conversation_id=inc.conversation_id,
        references_raw=(inc.headers or {}).get("references", ""),
        from_email=inc.from_email,
        from_name=inc.from_name or None,
        cc_raw=",".join(inc.cc or []),
        subject=(inc.subject or "")[:998],
        body=inc.body or "",
        received_at=to_utc(inc.received_at),   # sempre UTC no banco (Date: vem com o fuso do remetente, ex. -03:00)
        status=Status.RECEIVED,
    )
    db.add(rec)
    db.commit()
    return rec


def add_event(db: Session, rec: EmailRecord, event: str, description: str = "") -> None:
    db.add(ProcessingEvent(email_id=rec.id, event=event, description=description))
    db.commit()


def set_status(db: Session, rec: EmailRecord, status: str) -> None:
    rec.status = status
    rec.updated_at = utcnow()
    if status in Status.TERMINAL:
        rec.processed_at = utcnow()
    db.commit()


def count_document_requests(db: Session, conversation_id: str, event: str = "DOCUMENT_REQUESTED") -> int:
    stmt = (
        select(func.count(ProcessingEvent.id))
        .join(EmailRecord, EmailRecord.id == ProcessingEvent.email_id)
        .where(
            EmailRecord.conversation_id == conversation_id,
            ProcessingEvent.event == event,
        )
    )
    return db.scalar(stmt) or 0


def list_recent_emails(db: Session, limit: int = 50) -> list[EmailRecord]:
    return list(db.scalars(select(EmailRecord).order_by(EmailRecord.id.desc()).limit(limit)))


def get_state(db: Session, key: str) -> str | None:
    row = db.get(AppState, key)
    return row.value if row else None


def set_state(db: Session, key: str, value: str) -> None:
    row = db.get(AppState, key)
    if row is None:
        db.add(AppState(key=key, value=value))
    else:
        row.value = value
        row.updated_at = utcnow()
    db.commit()


def find_waiting_documents(db: Session, conversation_id: str, exclude_id: int) -> list[EmailRecord]:
    """E-mails anteriores, na mesma conversa, que ainda esperavam o CNPJ/CPF.
    Usado para juntar a mensagem original do cliente com a resposta que trouxe o documento."""
    stmt = (
        select(EmailRecord)
        .where(
            EmailRecord.conversation_id == conversation_id,
            EmailRecord.status == Status.WAITING_DOCUMENT,
            EmailRecord.id != exclude_id,
        )
        .order_by(EmailRecord.received_at, EmailRecord.id)
    )
    return list(db.scalars(stmt))


def list_retryable(db: Session, max_retries: int) -> list[EmailRecord]:
    """E-mails que falharam antes (ERROR ou REPLY_ERROR — ver Status.RETRYABLE)
    e ainda não esgotaram as tentativas. Sem isso, uma falha passageira (ex.:
    Gmail fora do ar na hora de responder) deixava o e-mail travado para
    sempre — ninguém tentava de novo sozinho."""
    stmt = (
        select(EmailRecord)
        .where(EmailRecord.status.in_(Status.RETRYABLE), EmailRecord.retry_count < max_retries)
        .order_by(EmailRecord.id)
    )
    return list(db.scalars(stmt))


def list_stale_waiting(db: Session, older_than) -> list[EmailRecord]:
    """Última mensagem de cada conversa que ainda está WAITING_DOCUMENT e é
    mais antiga que `older_than` — ou seja, o cliente nunca respondeu ao
    pedido de CNPJ/CPF. Usado pelo worker para escalar por TEMPO, sem
    depender de uma nova mensagem chegar (ver EmailProcessor.escalate_stale_waiting)."""
    stmt = (
        select(EmailRecord)
        .where(
            EmailRecord.status == Status.WAITING_DOCUMENT,
            EmailRecord.received_at < older_than,
        )
        .order_by(EmailRecord.conversation_id, EmailRecord.id.desc())
    )
    seen: set[str] = set()
    latest: list[EmailRecord] = []
    for rec in db.scalars(stmt):
        if rec.conversation_id in seen:
            continue
        seen.add(rec.conversation_id)
        latest.append(rec)
    return latest


def create_pre_atendimento(db: Session, *, email_id: int, **kwargs) -> PreAtendimento:
    """Idempotente: se já existe um pré-atendimento para este `email_id`
    (ex.: um retry reprocessando um e-mail que já tinha gerado o
    pré-atendimento antes de falhar em outro ponto do pipeline), devolve o
    existente em vez de criar outro duplicado para o mesmo chamado."""
    existing = db.scalar(select(PreAtendimento).where(PreAtendimento.email_id == email_id))
    if existing:
        return existing
    rec = PreAtendimento(email_id=email_id, **kwargs)
    db.add(rec)
    db.commit()
    return rec


def list_pre_atendimentos(db: Session, limit: int = 50) -> list[PreAtendimento]:
    stmt = select(PreAtendimento).order_by(PreAtendimento.id.desc()).limit(limit)
    return list(db.scalars(stmt))


def conversation_already_handled(db: Session, conversation_id: str) -> bool:
    """True se esta conversa já teve um e-mail VALIDADO (CUSTOMER_VALIDATED)
    antes. Evita que a NOVA fique pedindo CNPJ de novo, ou criando outro
    pré-atendimento, em cima de uma conversa já resolvida (ex.: cliente
    respondendo "obrigado").

    IMPORTANTE: só CUSTOMER_VALIDATED é tratado como terminal. HUMAN_REVIEW
    (CNPJ não encontrado, limite de tentativas, ou timeout por inatividade)
    fica em aberto de propósito: se o cliente responder depois com o
    documento certo, a NOVA deve validar normalmente, não ignorar a
    mensagem para sempre. Se HUMAN_REVIEW fosse terminal, um cliente que se
    corrigisse depois de uma escalada ficaria sem confirmação e sem
    pré-atendimento."""
    if not conversation_id:
        return False
    stmt = (
        select(EmailRecord.id)
        .where(
            EmailRecord.conversation_id == conversation_id,
            EmailRecord.status == Status.CUSTOMER_VALIDATED,
        )
        .limit(1)
    )
    return db.scalar(stmt) is not None


def thread_known_to_nova(db: Session, *, exclude_id: int, conversation_id: str | None,
                         reference_ids: list[str], since: datetime | None = None) -> bool:
    """True se a NOVA já tem, no banco, algum e-mail desta conversa (pela raiz da
    conversa ou por qualquer Message-ID citado em References/In-Reply-To).

    Serve para distinguir "conversa que nasceu depois do go-live" de "resposta
    dentro de uma conversa antiga, que talvez uma pessoa já tenha atendido".
    Registros ignorados por serem antigos ou escritos pela própria caixa não contam
    (Status.NOT_A_NOVA_THREAD), senão uma resposta humana ou um e-mail antigo
    \"autenticariam\" a conversa inteira."""
    ids = {i for i in [conversation_id, *reference_ids] if i}
    if not ids:
        return False
    conds = [
        EmailRecord.id != exclude_id,
        EmailRecord.status.notin_(Status.NOT_A_NOVA_THREAD),
        or_(EmailRecord.conversation_id.in_(ids), EmailRecord.message_id.in_(ids)),
    ]
    if since is not None:
        # só vale o que a NOVA viu DEPOIS do go-live; o que ficou de testes anteriores não conta
        # Compara pelo momento em que a NOVA GRAVOU o e-mail (relógio dela, sempre UTC), não pela data
        # do cabeçalho: o fuso do remetente e e-mails antigos baixados agora não confundem o go-live.
        conds.append(EmailRecord.created_at >= to_utc(since))
    return db.scalar(select(EmailRecord.id).where(*conds).limit(1)) is not None


def find_pending_reply_thread(db: Session, *, exclude_id: int, from_email: str,
                              subject: str, since: datetime | None = None) -> EmailRecord | None:
    """Recupera uma resposta que chegou com cabeçalhos/thread ID inconsistentes.

    Alguns provedores/clientes de e-mail não preservam a mesma raiz da conversa
    nos cabeçalhos IMAP. Se a NOVA pediu um CNPJ/CPF e a resposta do MESMO
    remetente chega como ``Re: mesmo assunto``, ainda podemos reconhecer a
    conversa pendente. A recuperação só é feita quando as mensagens pendentes
    com remetente+assunto apontam para uma única conversa; se houver ambiguidade,
    não adivinhamos e a proteção contra conversas antigas continua valendo.
    """
    sender = (from_email or "").strip().lower()
    wanted_subject = _normalize_thread_subject(subject)
    if not sender or not wanted_subject:
        return None

    stmt = select(EmailRecord).where(
        EmailRecord.id < exclude_id,
        EmailRecord.status == Status.WAITING_DOCUMENT,
        EmailRecord.from_email == sender,
    )
    if since is not None:
        stmt = stmt.where(EmailRecord.created_at >= to_utc(since))

    candidates = [
        rec for rec in db.scalars(stmt.order_by(EmailRecord.id.desc()))
        if _normalize_thread_subject(rec.subject) == wanted_subject
        and rec.conversation_id
    ]
    conversation_ids = {rec.conversation_id for rec in candidates}
    if len(conversation_ids) != 1:
        return None
    # Retorna a mensagem pendente mais recente, mas o chamador usa o ID canônico
    # da conversa (que é igual em todos os candidatos que passaram na regra).
    return candidates[0]


def _normalize_thread_subject(subject: str | None) -> str:
    value = (subject or "").strip()
    while True:
        stripped = re.sub(r"^\s*(?:re|res)\s*:\s*", "", value, count=1, flags=re.IGNORECASE)
        if stripped == value:
            break
        value = stripped.strip()
    return re.sub(r"\s+", " ", value).casefold()


def conversation_taken_by_team(db: Session, conversation_id: str | None, exclude_id: int) -> bool:
    """True se alguém da equipe já escreveu nesta conversa (IGNORED_TEAM)."""
    if not conversation_id:
        return False
    stmt = select(EmailRecord.id).where(
        EmailRecord.id != exclude_id,
        EmailRecord.conversation_id == conversation_id,
        EmailRecord.status == Status.IGNORED_TEAM,
    ).limit(1)
    return db.scalar(stmt) is not None


def had_human_review(db: Session, conversation_id: str, exclude_id: int) -> bool:
    """True se esta conversa já passou por HUMAN_REVIEW antes (CNPJ não
    encontrado, limite de tentativas, ou timeout). Usado só para registrar um
    evento informativo quando o cliente se corrige depois de uma escalada —
    não bloqueia nada (ver conversation_already_handled)."""
    if not conversation_id:
        return False
    stmt = (
        select(EmailRecord.id)
        .where(
            EmailRecord.conversation_id == conversation_id,
            EmailRecord.status == Status.HUMAN_REVIEW,
            EmailRecord.id != exclude_id,
        )
        .limit(1)
    )
    return db.scalar(stmt) is not None


def count_not_found_notifications(db: Session, from_email: str, document: str) -> int:
    """Quantas vezes a equipe já foi avisada de 'cliente não encontrado' para este
    remetente + este documento (em QUALQUER conversa - novos e-mails, não só
    respostas). Usado para não inundar a equipe se alguém insistir no mesmo
    CNPJ errado em mensagens novas (respostas na mesma conversa já são cortadas
    por conversation_already_handled, antes mesmo de chegar aqui)."""
    stmt = (
        select(func.count(ProcessingEvent.id))
        .join(EmailRecord, EmailRecord.id == ProcessingEvent.email_id)
        .where(
            EmailRecord.from_email == from_email,
            EmailRecord.cnpj_cpf == document,
            ProcessingEvent.event == "TEAM_NOTIFIED_NOT_FOUND",
        )
    )
    return db.scalar(stmt) or 0


# --------------------------------------------------------------------------
# Vínculo contato (e-mail/domínio) <-> CNPJ/CPF
# --------------------------------------------------------------------------
def get_links(db: Session, kind: str, value: str) -> list[ContactLink]:
    stmt = (select(ContactLink)
            .where(ContactLink.kind == kind, ContactLink.value == value)
            .order_by(ContactLink.id))
    return list(db.scalars(stmt))


def add_link(db: Session, *, kind: str, value: str, document: str, source: str = "AUTO",
             email_id: int | None = None) -> ContactLink | None:
    """Cria o vínculo; devolve None se ele já existia (idempotente — um retry não duplica)."""
    exists = db.scalar(select(ContactLink.id).where(
        ContactLink.kind == kind, ContactLink.value == value, ContactLink.document == document))
    if exists:
        return None
    link = ContactLink(kind=kind, value=value, document=document, source=source, first_email_id=email_id)
    db.add(link)
    db.commit()
    return link


def list_links(db: Session) -> list[ContactLink]:
    return list(db.scalars(select(ContactLink).order_by(ContactLink.document, ContactLink.kind, ContactLink.value)))


def delete_links(db: Session, value: str, document: str | None = None) -> int:
    stmt = select(ContactLink).where(ContactLink.value == value)
    if document:
        stmt = stmt.where(ContactLink.document == document)
    rows = list(db.scalars(stmt))
    for r in rows:
        db.delete(r)
    db.commit()
    return len(rows)
