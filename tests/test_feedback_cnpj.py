"""a NOVA sempre diz ao cliente se o CNPJ/CPF está errado (e por quê) ou certo (e qual empresa)."""
import pytest

from app.documents.validator import describe_invalid, find_invalid_document, looks_like_document
from app.rules.states import Status
from tests.helpers import make_email

ALPHA = "12.345.678/0001-95"


def _abre_conversa(env):
    o = make_email(subject="Aparelho com barulho", body="Meu aparelho está com barulho")
    assert env.processor.process(o) == Status.WAITING_DOCUMENT
    return o


def _responde(env, o, corpo):
    n0 = len(env.mail.outbox)
    r = make_email(conversation_id=o.conversation_id, subject="RE: Aparelho com barulho", body=corpo,
                   headers={"References": f"{o.message_id} <nova@x>", "In-Reply-To": "<nova@x>"})
    st = env.processor.process(r)
    return st, [m["body"] for m in env.mail.outbox[n0:]]


@pytest.mark.parametrize("digitado", ["12.345.678/0001-9", "12.345.678/0001-955", "1234567800019"])
def test_cnpj_com_quantidade_errada_diz_que_esta_errado(env, digitado):
    o = _abre_conversa(env)
    st, msgs = _responde(env, o, f"CNPJ: {digitado}")
    assert st == Status.WAITING_DOCUMENT and len(msgs) == 1
    assert "não parece estar correto" in msgs[0] and "caracteres" in msgs[0]


def test_digito_verificador_errado_repete_o_numero_e_o_motivo(env):
    o = _abre_conversa(env)
    st, msgs = _responde(env, o, "meu cnpj é 12.345.678/0001-96")
    assert "12.345.678/0001-96" in msgs[0] and "dígitos verificadores não conferem" in msgs[0]


def test_cpf_errado_nao_ecoa_o_numero_inteiro(env):
    o = _abre_conversa(env)
    st, msgs = _responde(env, o, "CPF 529.982.247-26")
    assert "não parece estar correto" in msgs[0]
    assert "529.982.247-26" not in msgs[0]


def test_cnpj_certo_diz_qual_empresa_foi_reconhecida(env):
    o = _abre_conversa(env)
    st, msgs = _responde(env, o, ALPHA)
    assert st == Status.CUSTOMER_VALIDATED
    assert "Confirmamos o seu cadastro" in msgs[0]
    assert "Empresa Alpha LTDA" in msgs[0] and ALPHA in msgs[0]


def test_cnpj_valido_mas_nao_cadastrado_diz_que_o_numero_esta_certo(env):
    o = _abre_conversa(env)
    st, msgs = _responde(env, o, "11.222.333/0001-81")
    assert st == Status.HUMAN_REVIEW
    assert "11.222.333/0001-81" in msgs[0] and "válido, mas não localizamos" in msgs[0]


def test_ao_esgotar_as_tentativas_o_cliente_e_avisado_uma_vez(env):
    o = _abre_conversa(env)
    todas = []
    for _ in range(4):
        st, msgs = _responde(env, o, "CNPJ 12.345.678/0001-96")
        todas += msgs
    avisos = [m for m in todas if "Não conseguimos validar" in m]
    assert len(avisos) == 1                      # avisou, e uma única vez
    assert st == Status.HUMAN_REVIEW


def test_remetente_conhecido_nao_precisa_de_cnpj_e_ve_o_nome_da_empresa(env, tmp_customers_file):
    tmp_customers_file.write_text(f"{ALPHA};Empresa Alpha LTDA;fulano@alpha.com\n", encoding="utf-8")
    e = make_email(from_email="fulano@alpha.com", subject="Sem internet", body="Estamos sem internet.")
    assert env.processor.process(e) == Status.CUSTOMER_VALIDATED
    corpo = env.mail.outbox[-1]["body"]
    assert "Empresa Alpha LTDA" in corpo and ALPHA not in corpo   # reconhece pelo e-mail; não expõe o CNPJ


def test_telefone_e_data_nao_sao_confundidos_com_cnpj():
    assert not looks_like_document("Ligue para (21) 98765-4321 amanhã, dia 15/10/2026.")
    assert not looks_like_document("Protocolo 202610150001 aberto às 14h, pode seguir com o atendimento.")
    assert find_invalid_document("CPF 123.456.78-9") == "123.456.78-9"


def test_descreve_o_motivo():
    assert "14" in describe_invalid("12.345.678/0001-9")
    assert "verificadores" in describe_invalid("12.345.678/0001-96")
