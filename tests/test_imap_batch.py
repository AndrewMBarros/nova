"""ImapSource.fetch() precisa pegar `uids[:limit]` (os MAIS ANTIGOS), não os mais
recentes. Como o SINCE do IMAP é por DIA, com mais e-mails que `batch_size` no mesmo
dia, pegar "os últimos N" deixaria os mais antigos de fora para sempre: o cursor
avança com base nos mais novos processados e o SINCE seguinte devolve o mesmo conjunto.

Este teste simula o IMAP (sem rede) e confirma que, com mais e-mails do que o
limite, o fetch() devolve os mais ANTIGOS primeiro.
"""
from datetime import datetime, timezone

from app.email.mime import build_message
from app.email.sources import ImapSource


class _FakeImap:
    """Simula só o suficiente de imaplib.IMAP4_SSL para o fetch()."""

    def __init__(self, uid_to_raw: dict[bytes, bytes]):
        self._uid_to_raw = uid_to_raw

    def login(self, *a, **k):
        pass

    def select(self, *a, **k):
        pass

    def logout(self):
        pass

    def uid(self, command, *args):
        if command == "SEARCH":
            all_uids = b" ".join(sorted(self._uid_to_raw))  # ordem crescente, como o IMAP real
            return "OK", [all_uids]
        if command == "FETCH":
            uid_arg = args[0]
            raw = self._uid_to_raw.get(uid_arg)
            if raw is None:
                return "NO", []
            return "OK", [(b"1 (UID %s BODY[] {%d}" % (uid_arg, len(raw)), raw)]
        raise AssertionError(f"comando IMAP inesperado: {command}")


def _raw_email(n: int) -> bytes:
    msg = build_message(sender="cliente@empresa.com", to="nova@suaempresa.com",
                         subject=f"Chamado {n}", body=f"corpo {n}")
    return msg.as_bytes()


def test_fetch_prioriza_os_mais_antigos_quando_ha_mais_que_o_limite(monkeypatch):
    base = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
    # 5 e-mails no mesmo dia, UIDs 101..105 em ordem crescente (mais antigo = UID menor).
    uid_to_raw = {
        f"{100 + i}".encode(): _raw_email(i)
        for i in range(1, 6)
    }

    source = ImapSource.__new__(ImapSource)  # evita exigir MAIL_USERNAME/MAIL_PASSWORD
    source.s = type("S", (), {"imap_host": "x", "imap_port": 993, "mark_read": False})()
    monkeypatch.setattr(source, "_connect", lambda: _FakeImap(uid_to_raw))

    resultado = source.fetch(since=base, limit=3)

    assert len(resultado) == 3
    assuntos = [incoming.subject for _, incoming in resultado]
    # Os 3 mais ANTIGOS (chamados 1, 2, 3), não os mais recentes (3, 4, 5).
    assert assuntos == ["Chamado 1", "Chamado 2", "Chamado 3"]


def test_fetch_drena_o_backlog_em_ciclos_sucessivos(monkeypatch):
    """Com limit=2 e 5 pendentes, dois ciclos (processando e removendo os já
    vistos da caixa simulada) devem avançar pelo backlog em ordem, sem pular
    nenhum -- é o comportamento que a correção garante ao longo do tempo."""
    base = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
    uid_to_raw = {
        f"{100 + i}".encode(): _raw_email(i)
        for i in range(1, 6)
    }
    source = ImapSource.__new__(ImapSource)
    source.s = type("S", (), {"imap_host": "x", "imap_port": 993, "mark_read": False})()
    monkeypatch.setattr(source, "_connect", lambda: _FakeImap(uid_to_raw))

    vistos: list[str] = []
    for _ in range(3):  # 3 ciclos de limit=2 cobrem os 5 pendentes
        pendentes = {k: v for k, v in uid_to_raw.items() if k.decode() not in vistos}
        monkeypatch.setattr(source, "_connect", lambda p=pendentes: _FakeImap(p))
        resultado = source.fetch(since=base, limit=2)
        if not resultado:
            break
        for handle, incoming in resultado:
            vistos.append(handle)

    assert len(vistos) == 5  # nenhum e-mail ficou órfão no backlog


def test_ack_evita_reler_sempre_os_mesmos_mais_antigos(monkeypatch):
    """Dia com mais e-mails que o limite, todos já tratados (DUPLICATE): com ack(), o fetch avança
    e alcança os novos, em vez de devolver sempre os mesmos `limit` mais antigos."""
    base = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
    uid_to_raw = {f"{100 + i}".encode(): _raw_email(i) for i in range(1, 6)}
    source = ImapSource.__new__(ImapSource)
    source.s = type("S", (), {"imap_host": "x", "imap_port": 993, "mark_read": False})()
    monkeypatch.setattr(source, "_connect", lambda: _FakeImap(uid_to_raw))

    vistos = []
    for _ in range(3):
        resultado = source.fetch(since=base, limit=2)
        for handle, _inc in resultado:
            source.ack(handle)
            vistos.append(handle)
    assert sorted(vistos) == ["101", "102", "103", "104", "105"]
