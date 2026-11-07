"""vínculo e-mail/domínio <-> CNPJ/CPF: quem já foi validado não precisa informar o CNPJ de novo."""
from app.database import repository as repo
from app.database.models import ContactLink, EmailRecord, PreAtendimento, ProcessingEvent
from app.rules.states import Status
from tests.conftest import CLIENTES_TESTE
from tests.helpers import make_email

ALPHA = "12.345.678/0001-95"
BETA = "98.765.432/0001-98"
ALPHA_N, BETA_N = "12345678000195", "98765432000198"


def events_of(env, message_id):
    with env.Session() as db:
        rec = db.query(EmailRecord).filter_by(message_id=message_id).one()
        return [e.event for e in db.query(ProcessingEvent).filter_by(email_id=rec.id).order_by(ProcessingEvent.id)]


def links(env):
    with env.Session() as db:
        return sorted((lk.kind, lk.value, lk.document) for lk in db.query(ContactLink))


def pre_atendimentos(env):
    with env.Session() as db:
        return db.query(PreAtendimento).order_by(PreAtendimento.id).all()


def valida_lucas(env, conv="a1"):
    """Fluxo completo: pede o CNPJ, o cliente responde -> valida e APRENDE o vínculo."""
    env.processor.process(make_email(conversation_id=conv, from_email="lucas@alpha.com"))
    env.processor.process(make_email(conversation_id=conv, from_email="lucas@alpha.com",
                                     subject="RE: Internet fora do ar", body=f"CNPJ: {ALPHA}"))


def test_primeiro_contato_sem_vinculo_pede_cnpj(env):
    e = make_email(from_email="lucas@alpha.com")
    assert env.processor.process(e) == Status.WAITING_DOCUMENT
    assert "CNPJ" in env.mail.outbox[0]["body"]
    assert links(env) == []


def test_validacao_pelo_cnpj_cria_vinculo_apenas_do_email(env):
    valida_lucas(env)
    assert links(env) == [("EMAIL", "lucas@alpha.com", ALPHA_N)]


def test_mesmo_email_em_nova_conversa_nao_pede_cnpj(env):
    valida_lucas(env)
    n = len(env.mail.outbox)
    novo = make_email(conversation_id="a2", from_email="lucas@alpha.com", body="Telefone sem sinal.")
    assert env.processor.process(novo) == Status.CUSTOMER_VALIDATED
    assert len(env.mail.outbox) == n + 1          # só a confirmação, nenhum pedido de CNPJ
    assert "confirmamos o seu cadastro" in env.mail.outbox[-1]["body"].lower()
    assert "CONTACT_LINK_USED" in events_of(env, novo.message_id)
    pre = pre_atendimentos(env)[-1]
    assert pre.cliente_documento == ALPHA_N and pre.cliente_nome == "Empresa Alpha LTDA"
    assert "Telefone sem sinal." in pre.observacoes
    assert pre.contato_email == "lucas@alpha.com"


def test_novo_email_do_mesmo_dominio_pede_cnpj_por_padrao(env):
    valida_lucas(env)
    colega = make_email(conversation_id="m1", from_email="pedro@alpha.com", from_name="Pedro",
                        body="Impressora parou.")
    assert env.processor.process(colega) == Status.WAITING_DOCUMENT
    assert "CNPJ" in env.mail.outbox[-1]["body"]
    assert len(pre_atendimentos(env)) == 1


def test_vinculo_automatico_de_dominio_so_quando_habilitado(env):
    env.processor.settings.link_domain_auto = True
    valida_lucas(env)
    assert ("DOMAIN", "alpha.com", ALPHA_N) in links(env)
    colega = make_email(conversation_id="m1", from_email="pedro@alpha.com", from_name="Pedro",
                        body="Impressora parou.")
    assert env.processor.process(colega) == Status.CUSTOMER_VALIDATED


def test_dominio_desconhecido_continua_pedindo_cnpj(env):
    valida_lucas(env)
    assert env.processor.process(make_email(from_email="alguem@beta-outra.com")) == Status.WAITING_DOCUMENT


def test_provedor_publico_vincula_so_o_email_exato(env):
    env.processor.process(make_email(conversation_id="g1", from_email="joao@gmail.com"))
    env.processor.process(make_email(conversation_id="g1", from_email="joao@gmail.com",
                                     subject="RE: x", body=f"CNPJ: {ALPHA}"))
    assert links(env) == [("EMAIL", "joao@gmail.com", ALPHA_N)]
    # o mesmo João, em outra conversa, é reconhecido...
    assert env.processor.process(make_email(conversation_id="g2", from_email="joao@gmail.com")) == Status.CUSTOMER_VALIDATED
    # ...mas outro usuário de Gmail NÃO herda o cliente
    assert env.processor.process(make_email(conversation_id="g3", from_email="maria@gmail.com")) == Status.WAITING_DOCUMENT


def test_email_salvo_tem_prioridade_sobre_o_cnpj_do_texto(env):
    """E-mail já salvo: valida por ele, sem olhar o CNPJ do texto."""
    valida_lucas(env)
    e = make_email(conversation_id="a3", from_email="lucas@alpha.com", body=f"Sou da Beta agora. CNPJ {BETA}")
    assert env.processor.process(e) == Status.CUSTOMER_VALIDATED
    assert pre_atendimentos(env)[-1].cliente_documento == ALPHA_N
    assert "DOCUMENT_IGNORED_LINK_USED" in events_of(env, e.message_id)
    assert ("EMAIL", "lucas@alpha.com", BETA_N) not in links(env)


def test_email_nao_salvo_valida_pelo_cnpj_informado(env):
    e = make_email(from_email="novo@beta-nova.com", body=f"Sem internet. CNPJ {BETA}")
    assert env.processor.process(e) == Status.CUSTOMER_VALIDATED
    assert pre_atendimentos(env)[-1].cliente_documento == BETA_N
    assert ("EMAIL", "novo@beta-nova.com", BETA_N) in links(env)


def test_email_ligado_a_dois_clientes_e_ambiguo_e_pede_cnpj(env):
    valida_lucas(env)
    with env.Session() as db:
        repo.add_link(db, kind="EMAIL", value="lucas@alpha.com", document=BETA_N, source="MANUAL")
    e = make_email(conversation_id="a4", from_email="lucas@alpha.com", body="Sem internet.")
    assert env.processor.process(e) == Status.WAITING_DOCUMENT
    assert "CONTACT_LINK_AMBIGUOUS" in events_of(env, e.message_id)


def test_cliente_removido_da_base_deixa_o_vinculo_velho(env, tmp_customers_file):
    valida_lucas(env)
    tmp_customers_file.write_text(CLIENTES_TESTE.replace("12.345.678/0001-95;Empresa Alpha LTDA\n", ""),
                                  encoding="utf-8")
    import os
    import time
    os.utime(tmp_customers_file, (time.time() + 5, time.time() + 5))  # garante novo mtime
    e = make_email(conversation_id="a5", from_email="lucas@alpha.com")
    assert env.processor.process(e) == Status.WAITING_DOCUMENT
    assert "CONTACT_LINK_STALE" in events_of(env, e.message_id)


def test_cnpj_nao_cadastrado_nao_cria_vinculo(env):
    env.processor.process(make_email(from_email="fulano@falso.com", body="CNPJ: 11.222.333/0001-81"))
    assert links(env) == []


def test_conversa_ja_validada_continua_sem_nova_pergunta(env):
    valida_lucas(env, conv="a1")
    n = len(env.mail.outbox)
    obrigado = make_email(conversation_id="a1", from_email="lucas@alpha.com", subject="RE: Internet fora do ar",
                          body="Obrigado!")
    assert env.processor.process(obrigado) == Status.ALREADY_HANDLED
    assert len(env.mail.outbox) == n


def test_interruptor_desliga_o_vinculo(env):
    env.processor.settings.contact_links_enabled = False
    valida_lucas(env)
    assert links(env) == []
    assert env.processor.process(make_email(conversation_id="z", from_email="lucas@alpha.com")) == Status.WAITING_DOCUMENT


def test_domain_auto_desligado_vincula_so_email(env):
    env.processor.settings.link_domain_auto = False
    valida_lucas(env)
    assert links(env) == [("EMAIL", "lucas@alpha.com", ALPHA_N)]
    assert env.processor.process(make_email(conversation_id="z", from_email="pedro@alpha.com")) == Status.WAITING_DOCUMENT


def test_dominio_aprendido_automaticamente_e_ignorado_com_a_opcao_desligada(env):
    """Domínios AUTO já gravados não liberam novos e-mails quando LINK_DOMAIN_AUTO está desligado."""
    valida_lucas(env)
    with env.Session() as db:
        repo.add_link(db, kind="DOMAIN", value="alpha.com", document=ALPHA_N, source="AUTO")
    novo = make_email(conversation_id="legado", from_email="novo@alpha.com")
    assert env.processor.process(novo) == Status.WAITING_DOCUMENT


def test_vinculo_manual_e_coluna_do_arquivo(env, tmp_customers_file):
    # manual, no banco
    with env.Session() as db:
        repo.add_link(db, kind="DOMAIN", value="beta.com.br", document=BETA_N, source="MANUAL")
    assert env.processor.process(make_email(from_email="ana@beta.com.br")) == Status.CUSTOMER_VALIDATED
    # 3ª coluna do clientes.txt
    tmp_customers_file.write_text(CLIENTES_TESTE + "44.455.566/0001-83;Empresa Zeta LTDA;@zeta-teste.com,chefe@x.com\n",
                                  encoding="utf-8")
    import os
    import time
    os.utime(tmp_customers_file, (time.time() + 5, time.time() + 5))
    assert env.processor.process(make_email(from_email="rita@zeta-teste.com")) == Status.CUSTOMER_VALIDATED
    assert env.processor.process(make_email(from_email="chefe@x.com")) == Status.CUSTOMER_VALIDATED


def test_so_o_remetente_que_informa_o_cnpj_e_vinculado(env):
    """Um CNPJ enviado por outra pessoa não comprova o vínculo do remetente anterior."""
    env.processor.process(make_email(conversation_id="r1", from_email="ana@gmail.com"))
    env.processor.process(make_email(conversation_id="r1", from_email="gerente@gmail.com",
                                     subject="RE: x", body=f"CNPJ {ALPHA}"))
    assert ("EMAIL", "gerente@gmail.com", ALPHA_N) in links(env)
    assert ("EMAIL", "ana@gmail.com", ALPHA_N) not in links(env)
    assert env.processor.process(make_email(conversation_id="r2", from_email="ana@gmail.com")) == Status.WAITING_DOCUMENT


def test_retry_nao_duplica_vinculo_nem_pre_atendimento(env):
    valida_lucas(env)
    with env.Session() as db:
        rec = db.query(EmailRecord).filter_by(status=Status.CUSTOMER_VALIDATED).order_by(EmailRecord.id.desc()).first()
        rec.status = Status.REPLY_ERROR
        db.commit()
    env.processor.retry_pending()
    assert len(links(env)) == 1
    assert len(pre_atendimentos(env)) == 1


def test_reply_to_conhecido_nao_substitui_identidade_do_remetente(env):
    valida_lucas(env)
    suspeito = make_email(conversation_id="reply-to", from_email="externo@desconhecido.com",
                          reply_to=["lucas@alpha.com"], body="Precisamos de suporte.")
    assert env.processor.process(suspeito) == Status.WAITING_DOCUMENT


def test_cnpj_incorreto_sempre_recebe_aviso_mesmo_apos_pedidos(env):
    c = "inv1"
    env.processor.process(make_email(conversation_id=c, from_email="lucas@teste-novo.com", body="Sem internet."))
    env.processor.process(make_email(conversation_id=c, from_email="lucas@teste-novo.com",
                                     subject="RE: Internet fora do ar", body="Boa tarde!"))
    n = len(env.mail.outbox)
    e = make_email(conversation_id=c, from_email="lucas@teste-novo.com", subject="RE: Internet fora do ar",
                   body="98.765.432/0001-97 - cnpj errado")
    assert env.processor.process(e) == Status.WAITING_DOCUMENT
    assert len(env.mail.outbox) == n + 1
    assert "não parece estar correto" in env.mail.outbox[-1]["body"]
