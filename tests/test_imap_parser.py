from app.email.parser import parse_rfc822

RAW = (
    b"From: Joao <Joao@Empresa.com>\r\n"
    b"To: nova@x.com\r\n"
    b"Reply-To: financeiro@empresa.com\r\n"
    b"Subject: =?utf-8?q?Re=3A_Internet_fora_do_ar?=\r\n"
    b"Message-ID: <resp1@empresa.com>\r\n"
    b"In-Reply-To: <nova1@x.com>\r\n"
    b"References: <orig@empresa.com> <nova1@x.com>\r\n"
    b"Date: Sat, 19 Sep 2026 12:00:00 -0300\r\n"
    b"Auto-Submitted: no\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n\r\n"
    b"CNPJ: 12.345.678/0001-95\r\n\r\n"
    b"Em sex., 18 de set. de 2026, NOVA escreveu:\r\n> texto antigo\r\n"
)


def test_parse_basico():
    e = parse_rfc822(RAW)
    assert e.message_id == "<resp1@empresa.com>"
    assert e.from_email == "joao@empresa.com"
    assert e.reply_to == ["financeiro@empresa.com"]
    assert e.subject == "Re: Internet fora do ar"
    assert e.body == "CNPJ: 12.345.678/0001-95"
    assert e.headers["auto-submitted"] == "no"
    assert e.graph_id == e.message_id


def test_conversa_usa_raiz_da_thread():
    assert parse_rfc822(RAW).conversation_id == "<orig@empresa.com>"


def test_sem_references_usa_proprio_id():
    raw = b"From: a@b.com\r\nMessage-ID: <x@b.com>\r\nSubject: oi\r\n\r\nSem internet\r\n"
    e = parse_rfc822(raw)
    assert e.conversation_id == "<x@b.com>" and e.body == "Sem internet"


def test_somente_html():
    raw = (b"From: a@b.com\r\nMessage-ID: <h@b.com>\r\nSubject: oi\r\n"
           b"Content-Type: text/html; charset=utf-8\r\n\r\n<p>Sem <b>internet</b></p>\r\n")
    assert parse_rfc822(raw).body == "Sem internet"


def test_sem_message_id_usa_fallback():
    e = parse_rfc822(b"From: a@b.com\r\nSubject: oi\r\n\r\ncorpo\r\n", fallback_id="42")
    assert e.message_id == "<imap-42@local>"
