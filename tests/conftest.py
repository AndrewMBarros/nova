from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.database.models import Base, EmailRecord
from app.email.sender import ConsoleMailGateway
from app.processor import EmailProcessor

NOVA = "nova@suaempresa.test"
TEAM = "suporte@suaempresa.test"

CLIENTES_TESTE = (
    "# comentário, deve ser ignorado\n"
    "\n"
    "12.345.678/0001-95;Empresa Alpha LTDA\n"
    "98.765.432/0001-98;Empresa Beta LTDA\n"
    "529.982.247-25;Cliente Gama (CPF)\n"
)


@pytest.fixture
def tmp_customers_file(tmp_path, monkeypatch):
    """Cria um data/clientes.txt temporário e faz app.customers.service usá-lo."""
    path = tmp_path / "clientes.txt"
    path.write_text(CLIENTES_TESTE, encoding="utf-8")
    from app.config import settings as global_settings
    monkeypatch.setattr(global_settings, "customers_file", str(path))
    return path


BLOQUEADOS_TESTE = (
    "# comentário\n"
    "\n"
    "@suaempresa.com.br\n"
    "alertas@sistema.com.br\n"
)


@pytest.fixture
def tmp_blocklist_file(tmp_path, monkeypatch):
    path = tmp_path / "bloqueados.txt"
    path.write_text(BLOQUEADOS_TESTE, encoding="utf-8")
    from app.config import settings as global_settings
    monkeypatch.setattr(global_settings, "blocked_senders_file", str(path))
    return path


@pytest.fixture
def env(tmp_customers_file, tmp_blocklist_file):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    settings = Settings(_env_file=None, nova_email=NOVA, team_email=TEAM, mail_mode="console",
                        max_document_requests=2)
    mail = ConsoleMailGateway()
    processor = EmailProcessor(Session, mail, settings)

    def status_of(message_id: str) -> str:
        with Session() as db:
            return db.query(EmailRecord).filter_by(message_id=message_id).one().status

    return SimpleNamespace(processor=processor, mail=mail, status_of=status_of, Session=Session)
