"""a NOVA não responde conversas anteriores ao go-live, nem respostas dentro delas."""
from datetime import datetime, timedelta, timezone

from app.rules.states import Status
from tests.helpers import make_email

ALPHA = "12.345.678/0001-95"


def test_resposta_em_conversa_antiga_nao_e_respondida(env):
    # cliente abriu ontem, alguém respondeu; hoje o cliente responde de novo (NOVA já no ar)
    resposta = make_email(
        conversation_id="<original-de-ontem@cliente>",
        subject="RE: Internet fora do ar",
        headers={"References": "<original-de-ontem@cliente> <resposta-humana@suaempresa>",
                 "In-Reply-To": "<resposta-humana@suaempresa>"},
    )
    assert env.processor.process(resposta) == Status.IGNORED_OLD_THREAD
    assert env.mail.outbox == []


def test_assunto_re_sem_cabecalhos_tambem_e_tratado_como_conversa_antiga(env):
    assert env.processor.process(make_email(subject="Re: Aparelho com barulho")) == Status.IGNORED_OLD_THREAD
    assert env.mail.outbox == []


def test_conversa_limpa_continua_sendo_atendida(env):
    assert env.processor.process(make_email(subject="Aparelho com barulho")) == Status.WAITING_DOCUMENT
    assert len(env.mail.outbox) == 1


def test_resposta_em_conversa_que_a_nova_iniciou_e_atendida(env):
    original = make_email(subject="Aparelho com barulho")
    assert env.processor.process(original) == Status.WAITING_DOCUMENT
    resposta = make_email(
        conversation_id=original.conversation_id,
        subject="RE: Aparelho com barulho",
        body=f"CNPJ {ALPHA}",
        headers={"References": f"{original.message_id} <resposta-da-nova@x>",
                 "In-Reply-To": "<resposta-da-nova@x>"},
    )
    assert env.processor.process(resposta) == Status.CUSTOMER_VALIDATED


def test_resposta_so_com_in_reply_to_do_original_tambem_conta(env):
    original = make_email()
    env.processor.process(original)
    resposta = make_email(conversation_id="<outra-raiz>", subject="RE: x", body=f"CNPJ {ALPHA}",
                          headers={"In-Reply-To": original.message_id})
    assert env.processor.process(resposta) == Status.CUSTOMER_VALIDATED


def test_varias_respostas_da_conversa_antiga_continuam_ignoradas(env):
    for _ in range(3):
        e = make_email(conversation_id="<antiga>", subject="RE: x",
                       headers={"References": "<antiga>"})
        assert env.processor.process(e) == Status.IGNORED_OLD_THREAD
    assert env.mail.outbox == []


def test_mensagem_da_propria_caixa_nao_legitima_conversa_antiga(env):
    from tests.conftest import NOVA
    humano = make_email(from_email=NOVA, conversation_id="<antiga>", subject="RE: x",
                        headers={"References": "<antiga>"})
    env.processor.process(humano)  # resposta humana saindo da mesma caixa
    cliente = make_email(conversation_id="<antiga>", subject="RE: x",
                         headers={"References": "<antiga> <humano>"})
    assert env.processor.process(cliente) == Status.IGNORED_OLD_THREAD
    assert env.mail.outbox == []


def test_interruptor_desliga_a_regra(env):
    env.processor.settings.ignore_unknown_replies = False
    assert env.processor.process(make_email(subject="RE: x")) == Status.WAITING_DOCUMENT


def test_resposta_com_assunto_igual_recupera_pedido_pendente_quando_raiz_muda(env):
    """Alguns clientes/provedores alteram a raiz da thread; a resposta ao
    pedido pendente deve ser processada, mas CNPJ inválido continua recusado."""
    from datetime import datetime, timedelta, timezone
    from app.database.models import EmailRecord, PreAtendimento

    env.processor.cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
    original = make_email(
        conversation_id="<raiz-original@cliente>",
        from_email="novo@cliente.com",
        subject="teste2",
        body="Estamos sem internet.",
    )
    assert env.processor.process(original) == Status.WAITING_DOCUMENT

    # Simula resposta verdadeira com References/In-Reply-To que não aponta para
    # o e-mail original, mas mesmo remetente e assunto (RE: é normalizado).
    invalido = make_email(
        conversation_id="<raiz-diferente@cliente>",
        from_email="novo@cliente.com",
        subject="Re: teste2",
        body="CNPJ 12.345.678/0001-96",
        headers={"in-reply-to": "<resposta-automatica-nao-registrada@nova>"},
    )
    assert env.processor.process(invalido) == Status.WAITING_DOCUMENT
    assert "não parece estar correto" in env.mail.outbox[-1]["body"].lower()

    # O documento correto pode vir em outra resposta cuja raiz ainda não bate.
    correto = make_email(
        conversation_id="<terceira-raiz@cliente>",
        from_email="novo@cliente.com",
        subject="RE: teste2",
        body="CNPJ 12.345.678/0001-95",
        headers={"in-reply-to": "<outra-resposta-automatica@nova>"},
    )
    assert env.processor.process(correto) == Status.CUSTOMER_VALIDATED

    with env.Session() as db:
        registros = db.query(EmailRecord).filter(
            EmailRecord.message_id.in_([original.message_id, invalido.message_id, correto.message_id])
        ).all()
        assert len({r.conversation_id for r in registros}) == 1
        assert db.query(PreAtendimento).count() == 1


def test_email_anterior_ao_corte_continua_ignorado(env):
    env.processor.cutoff = datetime.now(timezone.utc)
    velho = make_email(received_at=datetime.now(timezone.utc) - timedelta(days=1))
    assert env.processor.process(velho) == Status.IGNORED_OLD
    assert env.mail.outbox == []
