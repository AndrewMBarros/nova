from datetime import datetime, timezone

from app.timeutil import graph_dt, imap_date, parse_since, to_utc


def test_parse_since_vazio():
    assert parse_since("") is None and parse_since("  ") is None


def test_parse_since_com_fuso():
    dt = parse_since("2026-09-21T08:00:00-03:00")
    assert dt == datetime(2026, 9, 21, 11, 0, tzinfo=timezone.utc)


def test_parse_since_so_data():
    assert parse_since("2026-09-21").tzinfo is not None


def test_formato_imap_e_graph():
    dt = datetime(2026, 9, 3, 15, 30, 5, tzinfo=timezone.utc)
    assert imap_date(dt) == "03-Sep-2026"
    assert graph_dt(dt) == "2026-09-03T15:30:05Z"


def test_to_utc_converte_fuso():
    dt = datetime.fromisoformat("2026-09-21T23:00:00-03:00")
    assert to_utc(dt).day == 22
