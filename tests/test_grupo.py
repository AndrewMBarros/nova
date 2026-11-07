"""regra de grupo: De ou Cc de pessoas do Grupo Sigma cadastra direto no grupo."""
import pytest

from app.config import settings as global_settings
from app.database.models import EmailRecord, PreAtendimento, ProcessingEvent
from app.email.parser import parse_graph_message, parse_rfc822
from app.rules.states import Status
from tests.helpers import make_email

SIGMA = "33.344.455/0001-83"
SIGMA_N = "33344455000183"


@pytest.fixture(autouse=True)
def grupo(tmp_customers_file, tmp_path, monkeypatch):
    tmp_customers_file.write_text(tmp_customers_file.read_text(encoding="utf-8") +
                                  f"{SIGMA};Grupo Sigma\n", encoding="utf-8")
    g = tmp_path / "grupos.txt"
    g.write_text(f"{SIGMA};carlos@parceiro-exemplo.com.br,bruno.rocha@sigma-exemplo.com.br,"
                 "paulo.souza@sigma-exemplo.com.br,rafael.costa@sigma-exemplo.com.br\n", encoding="utf-8")
    monkeypatch.setattr(global_settings, "group_rules_file", str(g))


def eventos(env, mid):
    with env.Session() as db:
        rec = db.query(EmailRecord).filter_by(message_id=mid).one()
        return [e.event for e in db.query(ProcessingEvent).filter_by(email_id=rec.id)], rec.cnpj_cpf


def test_exemplo_rafael_com_carlos_em_cc(env):
    e = make_email(from_email="rafael.costa@sigma-exemplo.com.br", cc=["Carlos@parceiro-exemplo.com.br"],
                   subject="URGENTE - Ramais sem funcionar na loja Centro")
    assert env.processor.process(e) != Status.WAITING_DOCUMENT
    ev, doc = eventos(env, e.message_id)
    assert "GROUP_RULE_USED" in ev and doc == SIGMA_N
    with env.Session() as db:
        assert db.query(PreAtendimento).one().cliente_nome == "Grupo Sigma"


def test_cc_de_pessoa_do_grupo_com_remetente_externo(env):
    e = make_email(from_email="loja@qualquer.com", cc=["carlos@parceiro-exemplo.com.br"])
    env.processor.process(e)
    assert eventos(env, e.message_id)[1] == SIGMA_N


def test_remetente_do_grupo_sem_cc(env):
    e = make_email(from_email="Bruno.Rocha@sigma-exemplo.com.br")
    env.processor.process(e)
    assert eventos(env, e.message_id)[1] == SIGMA_N


def test_vale_mais_que_cnpj_de_outro_cliente_no_texto(env):
    e = make_email(from_email="carlos@parceiro-exemplo.com.br", body="CNPJ 12.345.678/0001-95 sem internet")
    env.processor.process(e)
    assert eventos(env, e.message_id)[1] == SIGMA_N


def test_sem_ninguem_do_grupo_continua_pedindo_cnpj(env):
    e = make_email(from_email="cliente@empresa.com", cc=["outro@parceiro-exemplo.com.br"])
    assert env.processor.process(e) == Status.WAITING_DOCUMENT


def test_parsers_leem_cc():
    g = parse_graph_message({"id": "1", "internetMessageId": "<a@b>", "from": {"emailAddress": {"address": "a@b.com"}},
                             "ccRecipients": [{"emailAddress": {"address": "Carlos@parceiro-exemplo.com.br"}}]})
    assert g.cc == ["carlos@parceiro-exemplo.com.br"]
    raw = b"From: a@b.com\nTo: s@x.com\nCc: Carlos Lima <Carlos@parceiro-exemplo.com.br>, d@x.com\nSubject: x\nMessage-ID: <1@x>\n\noi"
    assert parse_rfc822(raw).cc == ["carlos@parceiro-exemplo.com.br", "d@x.com"]
