"""Testes do fluxo principal: filtrar, pedir CNPJ/CPF e validar na base de clientes."""
from app.processor import DUPLICATE
from app.rules.states import Status
from tests.conftest import TEAM
from tests.helpers import make_email

ALPHA = "12.345.678/0001-95"        # cadastrado na base de teste (tests/conftest.py)
INEXISTENTE = "11.222.333/0001-81"  # válido, mas NÃO cadastrado


def test_sem_cnpj_solicita_documento(env):
    e = make_email()
    assert env.processor.process(e) == Status.WAITING_DOCUMENT
    assert len(env.mail.outbox) == 1
    assert "CNPJ" in env.mail.outbox[0]["body"]
    assert env.mail.outbox[0]["to"] == "cliente@empresa.com"


def test_cnpj_cadastrado_confirma_atendimento(env):
    e = make_email(body=f"CNPJ {ALPHA}\nEstamos sem internet.")
    assert env.processor.process(e) == Status.CUSTOMER_VALIDATED
    assert len(env.mail.outbox) == 1
    assert "providenciando o atendimento" in env.mail.outbox[0]["body"].lower()


def test_resposta_com_cnpj_e_validada(env):
    original = make_email(conversation_id="c1")
    env.processor.process(original)
    resposta = make_email(conversation_id="c1", subject="RE: Internet fora do ar", body=f"CNPJ: {ALPHA}")
    assert env.processor.process(resposta) == Status.CUSTOMER_VALIDATED
    assert env.status_of(resposta.message_id) == Status.CUSTOMER_VALIDATED


def test_cnpj_nao_cadastrado_recusa_e_avisa_equipe(env):
    e = make_email(body=f"CNPJ: {INEXISTENTE}")
    assert env.processor.process(e) == Status.HUMAN_REVIEW
    assert len(env.mail.outbox) == 2  # 1 para o cliente + 1 para a equipe
    to_cliente = [m for m in env.mail.outbox if m["to"] == "cliente@empresa.com"][0]
    assert "não localizamos" in to_cliente["body"].lower()
    assert "início ao seu atendimento" not in to_cliente["body"].lower()
    assert [m["to"] for m in env.mail.outbox if m["to"] == TEAM]


def test_noreply_nao_e_respondido(env):
    e = make_email(from_email="noreply@sistema.com", body=f"CNPJ {ALPHA}")
    assert env.processor.process(e) == Status.IGNORED_NOREPLY
    assert env.mail.outbox == []


def test_email_duplicado_e_ignorado(env):
    e = make_email(body=f"CNPJ {ALPHA}")
    assert env.processor.process(e) == Status.CUSTOMER_VALIDATED
    assert env.processor.process(e) == DUPLICATE
    assert len(env.mail.outbox) == 1


def test_limite_de_pedidos_de_cnpj_escala_para_equipe(env):
    for _ in range(2):
        assert env.processor.process(make_email(conversation_id="c9")) == Status.WAITING_DOCUMENT
    assert env.processor.process(make_email(conversation_id="c9")) == Status.HUMAN_REVIEW
    assert env.mail.outbox[-1]["to"] == TEAM


def test_responde_no_reply_to(env):
    e = make_email(reply_to=["financeiro@empresa.com"])
    env.processor.process(e)
    assert env.mail.outbox[0]["to"] == "financeiro@empresa.com"


def test_email_automatico_e_ignorado(env):
    e = make_email(headers={"Auto-Submitted": "auto-replied"})
    assert env.processor.process(e) == Status.IGNORED_AUTOMATED
    assert env.mail.outbox == []


def test_email_anterior_ao_corte_nao_e_respondido(env):
    from datetime import datetime, timedelta, timezone

    env.processor.cutoff = datetime.now(timezone.utc)
    velho = make_email(body=f"CNPJ {ALPHA}", received_at=datetime.now(timezone.utc) - timedelta(days=2))
    assert env.processor.process(velho) == Status.IGNORED_OLD
    assert env.mail.outbox == []

    novo = make_email(body=f"CNPJ {ALPHA}")
    assert env.processor.process(novo) == Status.CUSTOMER_VALIDATED


def test_pre_atendimento_e_salvo_com_os_campos_certos(env):
    from app.database.repository import list_pre_atendimentos

    e = make_email(from_name="Joao da Silva", body=f"CNPJ {ALPHA}\nEstamos sem internet desde as 14h.")
    env.processor.process(e)
    with env.Session() as db:
        pre = list_pre_atendimentos(db)
    assert len(pre) == 1
    p = pre[0]
    assert p.cliente_nome == "Empresa Alpha LTDA"
    assert p.contato_nome == "Joao da Silva"
    assert p.contato_email == "cliente@empresa.com"
    assert p.tipo_atendimento == "Suporte Técnico"
    assert p.canal == "E-mail"
    assert p.tipo_acesso == "Remoto"
    assert "sem internet" in p.observacoes.lower()


def test_pre_atendimento_junta_mensagem_original_e_resposta_com_cnpj(env):
    from app.database.repository import list_pre_atendimentos

    original = make_email(conversation_id="c2", body="Estamos sem internet desde as 14h.")
    env.processor.process(original)
    resposta = make_email(conversation_id="c2", subject="RE: Internet fora do ar", body=f"CNPJ: {ALPHA}")
    env.processor.process(resposta)
    with env.Session() as db:
        pre = list_pre_atendimentos(db)
    assert "sem internet" in pre[0].observacoes.lower()
    assert ALPHA.replace(".", "").replace("/", "").replace("-", "") in pre[0].observacoes.replace(".", "").replace("/", "").replace("-", "") or "CNPJ" in pre[0].observacoes


def test_numero_com_digito_errado_pede_para_reinformar(env):
    e = make_email(body="Meu CNPJ é 12.345.678/0001-90")  # dígito verificador errado de propósito
    assert env.processor.process(e) == Status.WAITING_DOCUMENT
    assert "não parece estar correto" in env.mail.outbox[0]["body"].lower()


def test_sem_numero_nenhum_pede_normalmente(env):
    e = make_email(body="Estamos sem internet, podem verificar?")
    assert env.processor.process(e) == Status.WAITING_DOCUMENT
    assert "não parece estar correto" not in env.mail.outbox[0]["body"].lower()


def test_conversa_ja_validada_nao_recebe_nova_resposta(env):
    e = make_email(conversation_id="c10", body=f"CNPJ {ALPHA}")
    assert env.processor.process(e) == Status.CUSTOMER_VALIDATED
    assert len(env.mail.outbox) == 1

    obrigado = make_email(conversation_id="c10", subject="RE: Internet fora do ar", body="Muito obrigado!")
    assert env.processor.process(obrigado) == Status.ALREADY_HANDLED
    assert len(env.mail.outbox) == 1  # não mandou nova resposta


def test_conversa_em_human_review_nao_fica_travada_para_sempre(env):
    """HUMAN_REVIEW (CNPJ não encontrado) não é tratado como terminal: se o
    cliente escrever de novo sem trazer o documento certo, a NOVA volta a
    pedir normalmente, em vez de ignorar a conversa para sempre (ver
    conversation_already_handled)."""
    e = make_email(conversation_id="c11", body=f"CNPJ: {INEXISTENTE}")
    assert env.processor.process(e) == Status.HUMAN_REVIEW

    outra = make_email(conversation_id="c11", subject="RE: Internet fora do ar", body="Alguma novidade?")
    assert env.processor.process(outra) == Status.WAITING_DOCUMENT

    # Mas, se ele finalmente mandar o CNPJ certo, a conversa valida normalmente.
    terceira = make_email(conversation_id="c11", body=f"CNPJ: {ALPHA}")
    assert env.processor.process(terceira) == Status.CUSTOMER_VALIDATED


def test_conversa_diferente_nao_e_afetada(env):
    e = make_email(conversation_id="c12", body=f"CNPJ {ALPHA}")
    env.processor.process(e)
    # Outra conversa, de OUTRA pessoa/empresa (o mesmo remetente já seria reconhecido pelo vínculo).
    outra_conversa = make_email(conversation_id="c13", from_email="desconhecido@outraempresa.com.br",
                                body="Estamos sem internet.")
    assert env.processor.process(outra_conversa) == Status.WAITING_DOCUMENT


def test_nao_encontrado_repetido_em_novas_conversas_avisa_equipe_so_uma_vez(env):
    e1 = make_email(from_email="mesmo@empresa.com", conversation_id="conv-a", body=f"CNPJ: {INEXISTENTE}")
    env.processor.process(e1)
    total_apos_primeiro = len([m for m in env.mail.outbox if m["to"] == TEAM])
    assert total_apos_primeiro == 1

    e2 = make_email(from_email="mesmo@empresa.com", conversation_id="conv-b", body=f"CNPJ: {INEXISTENTE}")
    assert env.processor.process(e2) == Status.HUMAN_REVIEW  # cliente ainda recebe a recusa
    total_apos_segundo = len([m for m in env.mail.outbox if m["to"] == TEAM])
    assert total_apos_segundo == 1  # mas a equipe NÃO recebe de novo

    cliente_respostas = [m for m in env.mail.outbox if m["to"] == "mesmo@empresa.com"]
    assert len(cliente_respostas) == 2  # o cliente é avisado nas duas vezes
