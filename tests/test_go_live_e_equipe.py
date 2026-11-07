"""go-live explícito (o que já está na caixa é antigo) e conversas assumidas pela equipe."""
from datetime import datetime, timedelta, timezone

from app.rules.states import Status
from tests.helpers import make_email

EQUIPE = "@suaempresa.test"


def _equipe(env):
    env.processor.settings.team_senders = EQUIPE


def test_equipe_nunca_recebe_resposta(env):
    _equipe(env)
    e = make_email(from_email="joao@suaempresa.test")
    assert env.processor.process(e) == Status.IGNORED_TEAM
    assert env.mail.outbox == []


def test_conversa_assumida_pela_equipe_nao_recebe_mais_a_nova(env):
    _equipe(env)
    original = make_email(subject="Aparelho com barulho")
    assert env.processor.process(original) == Status.WAITING_DOCUMENT  # NOVA pediu o CNPJ
    colega = make_email(from_email="joao@suaempresa.test", conversation_id=original.conversation_id,
                        subject="RE: Aparelho com barulho",
                        headers={"References": f"{original.message_id} <nova@x>"})
    assert env.processor.process(colega) == Status.IGNORED_TEAM
    enviados = len(env.mail.outbox)
    cliente = make_email(conversation_id=original.conversation_id, subject="RE: Aparelho com barulho",
                         body="12.345.678/0001-95",
                         headers={"References": f"{original.message_id} <nova@x> <joao@x>"})
    assert env.processor.process(cliente) == Status.ALREADY_HANDLED
    assert len(env.mail.outbox) == enviados


def test_conversa_de_antes_do_go_live_nao_conta_como_conhecida(env):
    # teste antigo: a NOVA processou a conversa ontem (corte antigo) ...
    ontem = datetime.now(timezone.utc) - timedelta(days=1)
    original = make_email(received_at=ontem, subject="Aparelho com barulho")
    assert env.processor.process(original) == Status.WAITING_DOCUMENT
    # ... hoje entra no ar de verdade: o corte vira "agora"
    env.processor.cutoff = datetime.now(timezone.utc)
    resposta = make_email(conversation_id=original.conversation_id, subject="RE: Aparelho com barulho",
                          received_at=env.processor.cutoff + timedelta(seconds=1),
                          headers={"References": original.message_id})
    assert env.processor.process(resposta) == Status.IGNORED_OLD_THREAD
    assert len(env.mail.outbox) == 1  # só o envio de ontem


def test_go_live_rearma_o_corte_para_agora(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app import worker
    from app.database import repository as repo
    from app.database.models import Base

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(worker, "SessionLocal", Session)
    monkeypatch.setattr(worker.settings, "process_from", "")
    antigo = (datetime.now(timezone.utc) - timedelta(days=11)).isoformat()
    with Session() as db:
        repo.set_state(db, "process_from", antigo)       # corte "grudado" de um teste antigo

    cutoff, _ = worker.load_window()
    assert cutoff < datetime.now(timezone.utc) - timedelta(days=10)   # sem --go-live: continua antigo

    cutoff, cursor = worker.load_window(go_live=True)
    assert datetime.now(timezone.utc) - cutoff < timedelta(minutes=1)
    assert cursor >= cutoff
    # e continua valendo na próxima partida, mesmo com um PROCESS_FROM antigo no .env
    monkeypatch.setattr(worker.settings, "process_from", antigo)
    cutoff2, _ = worker.load_window()
    assert cutoff2 >= cutoff
