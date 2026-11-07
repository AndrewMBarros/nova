"""Laço que lê a caixa da NOVA (IMAP ou Microsoft Graph) e processa os e-mails.

Lê por DATA a partir de um corte (PROCESS_FROM), sem depender de lido/não lido.

Uso:  python -m app.worker          (fica rodando)
      python -m app.worker --once   (um ciclo só, bom para testar)
"""
from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.database import repository as repo
from app.database.connection import SessionLocal, init_db
from app.deps import get_processor
from app.email.sources import MailSource, build_source
from app.timeutil import parse_since, to_utc

log = logging.getLogger("nova.worker")


def load_window(go_live: bool = False) -> tuple[datetime, datetime]:
    """Define o corte. `go_live=True` (python -m app.worker --go-live) re-arma o corte para AGORA:
    tudo o que já está na caixa passa a ser "conversa antiga" e a NOVA não se mete nelas.
    Esse momento fica gravado e vale mesmo que o .env tenha um PROCESS_FROM mais antigo."""
    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        if go_live:
            repo.set_state(db, "go_live_at", now.isoformat())
        configured = parse_since(settings.process_from)
        stored = repo.get_state(db, "process_from")
        if configured:
            cutoff = configured
        elif stored:
            cutoff = datetime.fromisoformat(stored)
        else:
            cutoff = now
        live = repo.get_state(db, "go_live_at")
        if live:
            cutoff = max(to_utc(cutoff), to_utc(datetime.fromisoformat(live)))
        repo.set_state(db, "process_from", cutoff.isoformat())

        saved_cursor = repo.get_state(db, "cursor")
        cursor = datetime.fromisoformat(saved_cursor) if saved_cursor else cutoff
        return cutoff, max(to_utc(cursor), to_utc(cutoff))


def save_cursor(cursor: datetime) -> None:
    with SessionLocal() as db:
        repo.set_state(db, "cursor", to_utc(cursor).isoformat())


def run_cycle(processor, source: MailSource, cursor: datetime, mark: bool) -> datetime:
    advance = True
    for handle, incoming in source.fetch(cursor, settings.batch_size):
        try:
            outcome = processor.process(incoming)
            log.info("%s | %s -> %s", incoming.from_email, incoming.subject[:60], outcome)
            if mark:
                source.mark_processed(handle)
            if advance:
                cursor = max(cursor, to_utc(incoming.received_at))
                save_cursor(cursor)
                source.ack(handle)
        except Exception:  # noqa: BLE001
            advance = False
            log.exception("Falha ao processar mensagem %s", handle)
    return cursor


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--go-live", action="store_true",
                        help="entrar no ar AGORA: tudo o que já está na caixa vira conversa antiga e é ignorado")
    args = parser.parse_args()

    init_db()
    source = build_source(settings)
    processor = get_processor()
    cutoff, cursor = load_window(go_live=args.go_live)
    processor.cutoff = cutoff
    mark = settings.mail_mode in ("graph", "imap")
    log.info("NOVA iniciada. Lendo e-mails a partir de %s",
             cutoff.astimezone().isoformat(timespec="seconds"))

    if to_utc(cutoff) < datetime.now(timezone.utc) - timedelta(hours=12):
        log.warning("ATENÇÃO: o corte é %s (há mais de 12h). Conversas da caixa a partir daí serão tratadas "
                    "como novas. Se a NOVA está ENTRANDO NO AR agora, rode: python -m app.worker --go-live",
                    cutoff.astimezone().isoformat(timespec="seconds"))

    while True:
        try:
            cursor = run_cycle(processor, source, cursor, mark)
            escalated = processor.escalate_stale_waiting()
            if escalated:
                log.info("%d conversa(s) escalada(s) para HUMAN_REVIEW por falta de resposta", escalated)
            retried = processor.retry_pending()
            if retried:
                log.info("%d e-mail(s) reprocessado(s) após erro anterior", retried)
        except Exception:  # noqa: BLE001
            log.exception("Erro no ciclo")
        if args.once:
            break
        time.sleep(settings.poll_interval_seconds)


if __name__ == "__main__":
    main()
