"""Escalonamento por tempo combinado com conversation_already_handled, retry automático
e idempotência do pré-atendimento."""
from datetime import datetime, timedelta, timezone

from app.database.models import EmailRecord, PreAtendimento
from app.rules.states import Status
from tests.conftest import TEAM
from tests.helpers import make_email

ALPHA = "12.345.678/0001-95"


def test_cliente_se_corrige_apos_escalonamento_por_tempo_e_validado(env):
    """O timeout escala para HUMAN_REVIEW; se o cliente responder DEPOIS com o
    CNPJ certo, a NOVA valida normalmente, não ignora."""
    env.processor.settings.stale_waiting_hours = 48
    conv = "sumiu-e-voltou"
    e1 = make_email(conversation_id=conv, message_id="<m1@cliente>")
    assert env.processor.process(e1) == Status.WAITING_DOCUMENT

    with env.Session() as db:
        rec = db.query(EmailRecord).filter_by(conversation_id=conv).one()
        rec.received_at = datetime.now(timezone.utc) - timedelta(hours=49)
        db.commit()
    assert env.processor.escalate_stale_waiting() == 1
    assert env.status_of(e1.message_id) == Status.HUMAN_REVIEW

    # Cliente aparece depois, na mesma conversa, com o CNPJ certo.
    e2 = make_email(conversation_id=conv, message_id="<m2@cliente>", body=f"CNPJ: {ALPHA}")
    assert env.processor.process(e2) == Status.CUSTOMER_VALIDATED  # não vira ALREADY_HANDLED
    with env.Session() as db:
        assert db.query(PreAtendimento).count() == 1


def test_obrigado_apos_validado_continua_ignorado(env):
    """Depois de CUSTOMER_VALIDATED, um "obrigado" na mesma conversa é ignorado (ALREADY_HANDLED)."""
    conv = "validado-normal"
    e1 = make_email(conversation_id=conv, body=f"CNPJ: {ALPHA}")
    assert env.processor.process(e1) == Status.CUSTOMER_VALIDATED

    antes = len(env.mail.outbox)
    e2 = make_email(conversation_id=conv, body="obrigado!")
    assert env.processor.process(e2) == Status.ALREADY_HANDLED
    assert len(env.mail.outbox) == antes  # nenhuma resposta nova


def test_limite_de_tentativas_ainda_escala_e_fica_assim_se_nao_responder(env):
    """Depois do DOCUMENT_LIMIT (sem nunca mandar nada certo), a conversa
    continua HUMAN_REVIEW -- não falsamente "ALREADY_HANDLED" encerrada, mas
    também não fica pedindo CNPJ pra sempre: silêncio do cliente = nada novo."""
    conv = "insistente"
    env.processor.process(make_email(conversation_id=conv, message_id="<a@c>"))
    env.processor.process(make_email(conversation_id=conv, message_id="<b@c>"))
    terceiro = env.processor.process(make_email(conversation_id=conv, message_id="<c@c>"))
    assert terceiro == Status.HUMAN_REVIEW
    assert any(m["to"] == TEAM for m in env.mail.outbox)


def test_retry_pending_reprocessa_email_em_erro(env):
    e = make_email()
    env.processor.process(e)
    with env.Session() as db:
        rec = db.query(EmailRecord).filter_by(message_id=e.message_id).one()
        rec.status = Status.ERROR
        rec.retry_count = 0
        db.commit()

    assert env.processor.retry_pending() == 1
    assert env.status_of(e.message_id) == Status.WAITING_DOCUMENT  # reprocessado normalmente


def test_retry_pending_tambem_pega_reply_error(env):
    """Status.RETRYABLE inclui ERROR e REPLY_ERROR: um e-mail que falhou ao ENVIAR
    a resposta (REPLY_ERROR) também é reprocessado automaticamente."""
    e = make_email()
    env.processor.process(e)
    with env.Session() as db:
        rec = db.query(EmailRecord).filter_by(message_id=e.message_id).one()
        rec.status = Status.REPLY_ERROR
        rec.retry_count = 0
        db.commit()

    assert env.processor.retry_pending() == 1
    assert env.status_of(e.message_id) == Status.WAITING_DOCUMENT


def test_falha_no_envio_vira_reply_error_nao_error_generico(env, monkeypatch):
    """ReplyError (falha ao enviar) vira Status.REPLY_ERROR, não o Status.ERROR
    genérico (usado para falhas de lógica/parsing)."""
    def _quebra(*a, **k):
        raise RuntimeError("SMTP fora do ar")
    monkeypatch.setattr(env.mail, "send_reply", _quebra)

    e = make_email()
    env.processor.process(e)
    assert env.status_of(e.message_id) == Status.REPLY_ERROR


def test_retry_pending_respeita_max_retries(env):
    env.processor.settings.max_retries = 2
    e = make_email()
    env.processor.process(e)
    with env.Session() as db:
        rec = db.query(EmailRecord).filter_by(message_id=e.message_id).one()
        rec.status = Status.ERROR
        rec.retry_count = 2  # já no limite
        db.commit()
    assert env.processor.retry_pending() == 0  # não tenta de novo


def test_create_pre_atendimento_e_idempotente(env):
    e = make_email(body=f"CNPJ: {ALPHA}")
    env.processor.process(e)
    with env.Session() as db:
        rec = db.query(EmailRecord).filter_by(message_id=e.message_id).one()
        from app.database import repository as repo
        # Chamar de novo para o MESMO email_id não deve criar um segundo registro.
        repo.create_pre_atendimento(
            db, email_id=rec.id, cliente_documento=ALPHA.replace(".", "").replace("/", "").replace("-", ""),
            cliente_nome="Empresa Alpha LTDA", contato_nome="", contato_email=rec.from_email,
            tipo_atendimento="Suporte Técnico", canal="E-mail", tipo_acesso="Remoto", observacoes="dup",
        )
        from app.database.models import PreAtendimento
        total = db.query(PreAtendimento).filter_by(email_id=rec.id).count()
        assert total == 1
