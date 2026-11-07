"""Cobre dois pontos do roteiro de teste focado em conversas:

- item 8: duas CNPJs diferentes na mesma mensagem -> usa o que está cadastrado.
- item 3: cliente nunca responde ao pedido de CNPJ -> escala por TEMPO, não só
  por número de tentativas (ver EmailProcessor.escalate_stale_waiting).
"""
from datetime import datetime, timedelta, timezone

from app.database.models import EmailRecord
from app.rules.states import Status
from tests.conftest import TEAM
from tests.helpers import make_email

ALPHA = "12.345.678/0001-95"        # cadastrado na base de teste
BETA = "98.765.432/0001-98"         # também cadastrado
INEXISTENTE = "11.222.333/0001-81"  # válido, mas não cadastrado


def test_dois_cnpjs_usa_o_cadastrado_quando_um_deles_nao_e(env):
    e = make_email(body=f"Segue o boleto do fornecedor CNPJ {INEXISTENTE}.\nNosso CNPJ é {ALPHA}.")
    assert env.processor.process(e) == Status.CUSTOMER_VALIDATED
    assert env.mail.outbox[-1]["to"] == "cliente@empresa.com"


def test_dois_cnpjs_cadastrados_usa_o_primeiro_que_aparece(env):
    e = make_email(body=f"CNPJ {BETA} ou, se preferir, CNPJ {ALPHA}.")
    assert env.processor.process(e) == Status.CUSTOMER_VALIDATED
    with env.Session() as db:
        rec = db.query(EmailRecord).filter_by(message_id=e.message_id).one()
        assert rec.cnpj_cpf == BETA.replace(".", "").replace("/", "").replace("-", "")


def test_dois_cnpjs_validos_porem_nenhum_cadastrado_vai_para_revisao(env):
    outro_nao_cadastrado = "11.444.777/0001-61"  # válido, também não cadastrado
    e = make_email(body=f"CNPJ {INEXISTENTE} ou CNPJ {outro_nao_cadastrado}.")
    assert env.processor.process(e) == Status.HUMAN_REVIEW


def test_cliente_que_nunca_responde_escala_por_tempo(env):
    env.processor.settings.stale_waiting_hours = 48
    e = make_email(conversation_id="sumiu-1")
    assert env.processor.process(e) == Status.WAITING_DOCUMENT
    assert env.processor.escalate_stale_waiting() == 0  # ainda dentro do prazo

    with env.Session() as db:
        rec = db.query(EmailRecord).filter_by(conversation_id="sumiu-1").one()
        rec.received_at = datetime.now(timezone.utc) - timedelta(hours=49)
        db.commit()

    assert env.processor.escalate_stale_waiting() == 1
    assert env.status_of(e.message_id) == Status.HUMAN_REVIEW
    assert any(m["to"] == TEAM for m in env.mail.outbox)

    # não escala de novo no próximo ciclo (já não está mais em WAITING_DOCUMENT)
    assert env.processor.escalate_stale_waiting() == 0


def test_escalonamento_desligado_com_stale_waiting_hours_zero(env):
    env.processor.settings.stale_waiting_hours = 0
    e = make_email(conversation_id="sumiu-2")
    env.processor.process(e)
    with env.Session() as db:
        rec = db.query(EmailRecord).filter_by(conversation_id="sumiu-2").one()
        rec.received_at = datetime.now(timezone.utc) - timedelta(days=30)
        db.commit()
    assert env.processor.escalate_stale_waiting() == 0
    assert env.status_of(e.message_id) == Status.WAITING_DOCUMENT
