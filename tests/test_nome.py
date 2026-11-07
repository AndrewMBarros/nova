"""identificação do cliente pelo NOME citado no e-mail (assinatura/apresentação).

Ordem: 1) e-mail/domínio vinculado  2) CNPJ/CPF no texto  3) NOME  4) pede o CNPJ/CPF.
"""
import os

import pytest

from app.database.models import ContactLink, EmailRecord, PreAtendimento, ProcessingEvent
from app.rules.states import Status
from tests.helpers import make_email

ALPHA = "12.345.678/0001-95"
OMEGA_DOC = "22233344000183"
VILA_DOC = "22233344000264"

CLIENTES = (
    "12.345.678/0001-95;Empresa Alpha LTDA;@alpha.com\n"
    "22.233.344/0001-83;Omega\n"
    "22.233.344/0003-45;Omega Pecas & Acessorios\n"
    "22.233.344/0002-64;Omega Vila Nova\n"
    "22.233.344/0004-26;Omega SÃO JOSÉ\n"
)

# Exemplo fictício (Gmail pessoal, só o nome da empresa na assinatura, telefone no fim)
ASSINATURA_OMEGA = (
    "Suporte;\nBom Dia !!!\n"
    "Os ramais 242 encontra-se mudo segundo a usuária Fulana e o ramal 226 o usuário Beltrano "
    "não consegue fazer ligações para outras UF ... podem ajudar ?\n"
    "Carlos Silva\nOmega Comercial Automotivo\n21-90000-0000"
)


@pytest.fixture
def base(env, tmp_customers_file):
    tmp_customers_file.write_text(CLIENTES, encoding="utf-8")
    st = tmp_customers_file.stat()
    os.utime(tmp_customers_file, (st.st_atime, st.st_mtime + 5))  # invalida o cache por mtime
    return env


def events_of(env, message_id):
    with env.Session() as db:
        rec = db.query(EmailRecord).filter_by(message_id=message_id).one()
        return [e.event for e in db.query(ProcessingEvent).filter_by(email_id=rec.id).order_by(ProcessingEvent.id)]


def pres(env):
    with env.Session() as db:
        return db.query(PreAtendimento).order_by(PreAtendimento.id).all()


def test_caso_omega_gmail_pessoal_sem_cnpj_e_identificado_pelo_nome(base):
    e = make_email(from_email="carlos.silva@gmail.com", from_name="Carlos Silva",
                   subject="Suporte;", body=ASSINATURA_OMEGA)
    assert base.processor.process(e) == Status.CUSTOMER_VALIDATED
    pre = pres(base)[-1]
    assert pre.cliente_nome == "Omega" and pre.cliente_documento == OMEGA_DOC
    assert pre.observacoes.startswith("[CONFIRMAR CLIENTE]")
    assert "ramais 242" in pre.observacoes
    assert "CUSTOMER_MATCHED_BY_NAME" in events_of(base, e.message_id)
    resposta = base.mail.outbox[-1]["body"]
    assert "Omega" in resposta and "CNPJ" not in resposta and "22.233" not in resposta   # nada além do que ele disse


def test_nome_nao_cria_vinculo_de_email(base):
    base.processor.process(make_email(from_email="carlos.silva@gmail.com", body=ASSINATURA_OMEGA))
    with base.Session() as db:
        assert db.query(ContactLink).count() == 0


def test_filial_especifica_vence_o_cadastro_generico(base):
    e = make_email(from_email="fulano@gmail.com", body="Ramal mudo.\nOmega Vila Nova")
    assert base.processor.process(e) == Status.CUSTOMER_VALIDATED
    assert pres(base)[-1].cliente_documento == VILA_DOC


def test_sem_nome_conhecido_pede_cnpj(base):
    e = make_email(from_email="fulano@gmail.com", from_name="Fulano", body="Estamos sem internet.")
    assert base.processor.process(e) == Status.WAITING_DOCUMENT
    assert "CNPJ" in base.mail.outbox[-1]["body"]
    assert pres(base) == []


def test_nome_nao_cadastrado_pede_cnpj(base):
    e = make_email(from_email="fulano@gmail.com", body="Sem internet.\nPadaria Pao Quente")
    assert base.processor.process(e) == Status.WAITING_DOCUMENT


def test_nome_generico_nao_casa(base):
    e = make_email(from_email="fulano@gmail.com", body="Sem internet.\nComercial Automotivo")
    assert base.processor.process(e) == Status.WAITING_DOCUMENT


def test_nome_ambiguo_pede_cnpj(base, tmp_customers_file):
    tmp_customers_file.write_text(CLIENTES + "99.999.999/0001-91;Omega\n", encoding="utf-8")
    st = tmp_customers_file.stat()
    os.utime(tmp_customers_file, (st.st_atime, st.st_mtime + 10))
    # dois cadastros chamados "Omega" com documentos diferentes -> empate -> não chuta
    e = make_email(from_email="fulano@gmail.com", body=ASSINATURA_OMEGA)
    assert base.processor.process(e) == Status.WAITING_DOCUMENT
    assert "CUSTOMER_NAME_AMBIGUOUS" in events_of(base, e.message_id)


def test_vinculo_de_dominio_tem_prioridade_sobre_o_nome(base):
    e = make_email(from_email="x@alpha.com", body="Sem internet.\nOmega Comercial Automotivo")
    assert base.processor.process(e) == Status.CUSTOMER_VALIDATED
    assert pres(base)[-1].cliente_nome == "Empresa Alpha LTDA"
    assert "CUSTOMER_MATCHED_BY_NAME" not in events_of(base, e.message_id)


def test_cnpj_no_texto_tem_prioridade_sobre_o_nome(base):
    e = make_email(from_email="fulano@gmail.com", body=f"CNPJ {ALPHA}\nSem internet.\nOmega Comercial Automotivo")
    assert base.processor.process(e) == Status.CUSTOMER_VALIDATED
    assert pres(base)[-1].cliente_nome == "Empresa Alpha LTDA"


def test_cnpj_incorreto_recebe_aviso_mesmo_citando_nome(base):
    e = make_email(from_email="fulano@gmail.com", body="Meu CNPJ é 12.345.678/0001-96\nOmega Comercial Automotivo")
    assert base.processor.process(e) == Status.WAITING_DOCUMENT
    assert "CUSTOMER_MATCHED_BY_NAME" not in events_of(base, e.message_id)


def test_recurso_pode_ser_desligado(base):
    base.processor.settings.name_match_enabled = False
    e = make_email(from_email="fulano@gmail.com", body=ASSINATURA_OMEGA)
    assert base.processor.process(e) == Status.WAITING_DOCUMENT


def test_nome_citado_no_meio_do_texto_sem_apresentacao_nao_vale(base):
    corpo = "Falei com a Omega ontem sobre isso.\n" + "linha\n" * 8 + "Att"
    e = make_email(from_email="fulano@gmail.com", body=corpo)
    assert base.processor.process(e) == Status.WAITING_DOCUMENT
