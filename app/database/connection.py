from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database.models import Base


def make_engine(url: str):
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, pool_pre_ping=True, **kwargs)


engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _auto_add_missing_columns() -> None:
    """Completa um banco SQLite existente: create_all() cria TABELAS novas, mas nunca
    adiciona COLUNAS novas a uma tabela que já existe. Sem isto, um `nova.db` criado
    antes de uma coluna nova passaria a dar erro (silencioso, dentro do worker) ao
    gravar esse campo. Só roda no SQLite; com PostgreSQL o certo é usar migrações (Alembic)."""
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # tabela nova: create_all() já cuidou dela
            existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_cols:
                    continue
                col_type = column.type.compile(engine.dialect)
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'))


def init_db() -> None:
    Base.metadata.create_all(engine)
    _auto_add_missing_columns()
