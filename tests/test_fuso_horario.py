"""o fuso do remetente (Date: ... -0300) não pode fazer a NOVA ignorar a resposta do CNPJ."""
from datetime import datetime, timedelta, timezone

from app.database.models import EmailRecord
from app.rules.states import Status
from tests.helpers import make_email

BR = timezone(timedelta(hours=-3))
ALPHA = "12.345.678/0001-95"


def _go_live(env):
    env.processor.cutoff = datetime.now(timezone.utc) - timedelta(minutes=1)


def _fluxo_gmail(env, corpo_resposta, *, agora=None):
    """Cliente novo escreve (Date com -03:00, como o Gmail), a NOVA pede o CNPJ, o cliente responde."""
    agora = (agora or datetime.now(timezone.utc)).astimezone(BR)
    o = make_email(from_email="cliente.teste@gmail.com", subject="teste 4", body="oi", received_at=agora)
    assert env.processor.process(o) == Status.WAITING_DOCUMENT
    r = make_email(from_email="cliente.teste@gmail.com", conversation_id=o.conversation_id, subject="Re: teste 4",
                   body=f"{corpo_resposta}\n\nEm sex., 16 de out. de 2026 às 16:37, Cliente Teste <cliente.teste@gmail.com> escreveu:",
                   received_at=agora + timedelta(minutes=1),
                   headers={"References": f"{o.message_id} <nova1@gmail.com>", "In-Reply-To": "<nova1@gmail.com>"})
    return env.processor.process(r)


def test_resposta_com_cnpj_certo_e_validada_mesmo_com_data_em_fuso_brasileiro(env):
    _go_live(env)
    assert _fluxo_gmail(env, ALPHA) == Status.CUSTOMER_VALIDATED


def test_resposta_com_cnpj_errado_recebe_aviso_mesmo_com_fuso_brasileiro(env):
    _go_live(env)
    assert _fluxo_gmail(env, "12.345.678/0001-96") == Status.WAITING_DOCUMENT
    assert "não parece estar correto" in env.mail.outbox[-1]["body"]


def test_banco_guarda_a_data_em_utc(env):
    e = make_email(received_at=datetime(2026, 10, 16, 16, 44, tzinfo=BR))
    env.processor.process(e)
    with env.Session() as db:
        rec = db.query(EmailRecord).filter_by(message_id=e.message_id).one()
    assert rec.received_at.replace(tzinfo=None) == datetime(2026, 10, 16, 19, 44)


def test_conversa_aberta_antes_de_um_novo_go_live_nao_vale_depois_dele(env):
    # teste antigo gravado ANTES do go-live novo; resposta chega depois: conversa antiga -> ignorada
    agora = datetime.now(timezone.utc)
    o = make_email(from_email="cliente.teste@gmail.com", subject="teste 3", received_at=agora.astimezone(BR))
    env.processor.process(o)
    env.processor.cutoff = datetime.now(timezone.utc)   # re-armou com --go-live
    r = make_email(from_email="cliente.teste@gmail.com", conversation_id=o.conversation_id, subject="Re: teste 3",
                   body=ALPHA, received_at=env.processor.cutoff.astimezone(BR) + timedelta(seconds=1),
                   headers={"References": o.message_id})
    assert env.processor.process(r) == Status.IGNORED_OLD_THREAD


def test_resposta_colando_a_linha_do_clientes_txt_e_com_citacao_do_gmail(env):
    """O que o cliente de teste realmente mandou: 'CNPJ;NOME' + a citação 'Em sex., ... escreveu:'."""
    _go_live(env)
    assert _fluxo_gmail(env, f"{ALPHA};EMPRESA ALPHA LTDA") == Status.CUSTOMER_VALIDATED
