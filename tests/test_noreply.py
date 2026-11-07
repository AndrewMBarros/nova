import pytest

from app.rules.engine import Action, is_noreply, pre_check
from tests.helpers import make_email


@pytest.mark.parametrize("addr", [
    "noreply@empresa.com", "no-reply@empresa.com", "no_reply@x.com",
    "naoresponda@x.com", "nao-responda@x.com", "donotreply@x.com",
    "do-not-reply@x.com", "mailer-daemon@x.com", "postmaster@x.com",
])
def test_detecta_noreply(addr):
    assert is_noreply(addr)


def test_endereco_normal_nao_e_noreply():
    assert not is_noreply("joao.silva@empresa.com")


def test_noreply_e_ignorado():
    r = pre_check(make_email(from_email="noreply@sistema.com"), nova_email="nova@x.com")
    assert r.action is Action.IGNORE_NOREPLY


def test_remetente_normal_prossegue():
    r = pre_check(make_email(), nova_email="nova@x.com")
    assert r.action is Action.PROCEED and r.reply_address == "cliente@empresa.com"


def test_reply_to_tem_prioridade():
    r = pre_check(make_email(reply_to=["financeiro@empresa.com"]), nova_email="nova@x.com")
    assert r.reply_address == "financeiro@empresa.com"


def test_reply_to_noreply_cai_no_from():
    r = pre_check(make_email(reply_to=["noreply@empresa.com"]), nova_email="nova@x.com")
    assert r.action is Action.PROCEED and r.reply_address == "cliente@empresa.com"


def test_ignora_proprio_email():
    r = pre_check(make_email(from_email="NOVA@x.com"), nova_email="nova@x.com")
    assert r.action is Action.IGNORE_SELF


@pytest.mark.parametrize("headers", [
    {"Auto-Submitted": "auto-replied"},
    {"Precedence": "bulk"},
    {"List-Id": "<lista.empresa.com>"},
])
def test_ignora_automaticos(headers):
    r = pre_check(make_email(headers=headers), nova_email="nova@x.com")
    assert r.action is Action.IGNORE_AUTOMATED


def test_auto_submitted_no_nao_bloqueia():
    r = pre_check(make_email(headers={"Auto-Submitted": "no"}), nova_email="nova@x.com")
    assert r.action is Action.PROCEED


def test_ignora_assunto_bloqueado():
    e = make_email(subject="[Alerta] Relatório diário do sistema")
    r = pre_check(e, nova_email="nova@x.com", blocked_subjects=["relatório diário"])
    assert r.action is Action.IGNORE_BLOCKED
    assert pre_check(make_email(), nova_email="nova@x.com", blocked_subjects=["relatório diário"]).action is Action.PROCEED


def test_piloto_so_processa_remetentes_permitidos():
    lista = ["meu.email@gmail.com", "@suaempresa.com.br"]
    fora = pre_check(make_email(from_email="cliente@empresa.com"), nova_email="n@x.com", only_senders=lista)
    assert fora.action is Action.IGNORE_BLOCKED
    assert pre_check(make_email(from_email="meu.email@gmail.com"), nova_email="n@x.com", only_senders=lista).action is Action.PROCEED
    assert pre_check(make_email(from_email="colega@suaempresa.com.br"), nova_email="n@x.com", only_senders=lista).action is Action.PROCEED
