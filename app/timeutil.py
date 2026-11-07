"""Funções de data usadas para o corte (PROCESS_FROM) e o cursor de leitura."""
from __future__ import annotations

from datetime import datetime, timezone

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def to_utc(dt: datetime) -> datetime:
    """Converte para UTC. Data sem fuso é interpretada como horário local da máquina."""
    return dt.astimezone(timezone.utc)


def parse_since(value: str) -> datetime | None:
    value = (value or "").strip()
    return to_utc(datetime.fromisoformat(value)) if value else None


def imap_date(dt: datetime) -> str:
    """Formato do IMAP SEARCH SINCE (só a data, meses em inglês): 21-Sep-2026."""
    dt = to_utc(dt)
    return f"{dt.day:02d}-{_MONTHS[dt.month - 1]}-{dt.year}"


def graph_dt(dt: datetime) -> str:
    return to_utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ")
