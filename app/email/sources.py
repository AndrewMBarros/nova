"""De onde a NOVA lê e-mails: Microsoft Graph ou IMAP.

A leitura é por DATA (a partir de um ponto de partida), nunca por "não lido":
na caixa compartilhada do suporte a equipe abre e-mails sem que a NOVA já os tenha tratado.
A duplicidade é evitada pelo Message-ID no banco.
"""
from __future__ import annotations

import imaplib
import logging
from abc import ABC, abstractmethod
from datetime import datetime

from app.config import Settings
from app.email.models import IncomingEmail
from app.email.parser import parse_graph_message, parse_rfc822
from app.timeutil import imap_date

log = logging.getLogger("nova.source")


class MailSource(ABC):
    @abstractmethod
    def fetch(self, since: datetime, limit: int) -> list[tuple[str, IncomingEmail]]:
        """Devolve (identificador, e-mail) recebidos a partir de `since`, mais antigos primeiro."""

    @abstractmethod
    def mark_processed(self, handle: str) -> None:
        """Marca (se configurado) o e-mail como tratado pela NOVA."""

    def ack(self, handle: str) -> None:
        """Avisa que o e-mail foi tratado (e todos os anteriores também); a fonte pode pular até ele."""


class GraphSource(MailSource):
    def __init__(self, graph, s: Settings) -> None:
        self.graph = graph
        self.s = s
        self._categories: dict[str, list[str]] = {}

    def fetch(self, since: datetime, limit: int) -> list[tuple[str, IncomingEmail]]:
        out = []
        for msg in self.graph.list_since(since, top=limit):
            try:
                self._categories[msg["id"]] = list(msg.get("categories") or [])
                out.append((msg["id"], parse_graph_message(msg)))
            except Exception:  # noqa: BLE001
                log.exception("Falha ao interpretar mensagem %s", msg.get("id"))
        return out

    def mark_processed(self, handle: str) -> None:
        if self.s.mark_read:
            self.graph.mark_read(handle)
        if self.s.mark_category:
            self.graph.add_category(handle, self._categories.get(handle, []), self.s.mark_category)


class ImapSource(MailSource):
    """Lê a caixa por IMAP (ex.: Gmail). Usa BODY.PEEK: ler não marca como lido."""

    def __init__(self, s: Settings) -> None:
        if not s.mail_username or not s.mail_password:
            raise ValueError("Defina MAIL_USERNAME e MAIL_PASSWORD (senha de aplicativo) no .env")
        self.s = s
        self._last_uid = 0

    def _connect(self) -> imaplib.IMAP4_SSL:
        conn = imaplib.IMAP4_SSL(self.s.imap_host, self.s.imap_port)
        conn.login(self.s.mail_username, self.s.mail_password.replace(" ", ""))
        conn.select("INBOX")
        return conn

    def fetch(self, since: datetime, limit: int) -> list[tuple[str, IncomingEmail]]:
        # O IMAP só filtra por DIA; o corte exato é feito pela NOVA (cutoff) e pelo Message-ID.
        conn = self._connect()
        out: list[tuple[str, IncomingEmail]] = []
        try:
            typ, data = conn.uid("SEARCH", None, "SINCE", imap_date(since))
            uids = data[0].split() if typ == "OK" and data and data[0] else []
            # Pega os `limit` MAIS ANTIGOS (FIFO), não os mais recentes: como o
            # SINCE do IMAP é por DIA (não por minuto), se houver mais de
            # `limit` e-mails pendentes no mesmo dia, pegar "os últimos" deixa
            # os mais antigos permanentemente de fora -- o cursor avança para a
            # data dos mais novos processados, e os antigos não entram em
            # nenhum SINCE seguinte. Com os mais antigos primeiro, o backlog é
            # drenado progressivamente a cada ciclo até zerar.
            # Já tratados neste processo (UID <= _last_uid) não voltam: sem isso, num dia com
            # mais de `limit` e-mails os `limit` mais antigos seriam relidos (DUPLICATE) para
            # sempre e os mais novos nunca chegariam a ser processados.
            uids = [u for u in uids if int(u) > getattr(self, "_last_uid", 0)]
            for uid in uids[:limit]:
                typ, msgdata = conn.uid("FETCH", uid, "(BODY.PEEK[])")
                if typ != "OK" or not msgdata or not isinstance(msgdata[0], tuple):
                    continue
                try:
                    out.append((uid.decode(), parse_rfc822(msgdata[0][1], fallback_id=uid.decode())))
                except Exception:  # noqa: BLE001
                    log.exception("Falha ao interpretar e-mail UID %s", uid)
        finally:
            conn.logout()
        out.sort(key=lambda item: item[1].received_at)
        return out

    def ack(self, handle: str) -> None:
        try:
            self._last_uid = max(getattr(self, "_last_uid", 0), int(handle))
        except ValueError:
            pass

    def mark_processed(self, handle: str) -> None:
        if not self.s.mark_read:
            return
        conn = self._connect()
        try:
            conn.uid("STORE", handle, "+FLAGS", "(\\Seen)")
        finally:
            conn.logout()

    def summary(self, limit: int = 5) -> tuple[int, list[str]]:
        """Para o imap_check: total de não lidos e cabeçalhos dos primeiros (só leitura)."""
        conn = self._connect()
        try:
            typ, data = conn.uid("SEARCH", None, "UNSEEN")
            uids = data[0].split() if typ == "OK" and data and data[0] else []
            lines = []
            for uid in uids[:limit]:
                typ, d = conn.uid("FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                if typ == "OK" and d and isinstance(d[0], tuple):
                    lines.append(" | ".join(d[0][1].decode(errors="replace").split("\r\n")).strip(" |"))
            return len(uids), lines
        finally:
            conn.logout()


def build_source(s: Settings) -> MailSource:
    if s.mail_mode.startswith("graph"):
        from app.microsoft.graph import build_graph_client

        return GraphSource(build_graph_client(), s)
    if s.mail_mode.startswith("imap"):
        return ImapSource(s)
    raise SystemExit("Defina MAIL_MODE=imap_readonly, imap, graph_readonly ou graph no .env")
