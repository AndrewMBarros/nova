from app.email.mime import build_message


def test_resposta_mantem_thread_e_marca_como_automatica():
    m = build_message(sender="nova@x.com", to="cliente@y.com", subject="Re: oi",
                      body="Olá", in_reply_to="<orig@y.com>")
    assert m["To"] == "cliente@y.com" and m["From"] == "nova@x.com"
    assert m["In-Reply-To"] == "<orig@y.com>" and m["References"] == "<orig@y.com>"
    assert m["Auto-Submitted"] == "auto-replied"
    assert m["Message-ID"].endswith("@x.com>")
    assert "Olá" in m.get_content()


def test_sem_in_reply_to_invalido():
    m = build_message(sender="nova@x.com", to="a@b.com", subject="s", body="c", in_reply_to="abc")
    assert m["In-Reply-To"] is None


def test_aviso_para_equipe_e_auto_generated():
    m = build_message(sender="nova@x.com", to="suporte@x.com", subject="s", body="c",
                      auto_submitted="auto-generated")
    assert m["Auto-Submitted"] == "auto-generated"


def test_reply_to_e_nome_do_remetente():
    m = build_message(sender="nova@gmail.com", to="c@y.com", subject="s", body="c",
                      reply_to="suporte@suaempresa.com.br", sender_name="NOVA - Suporte")
    assert m["Reply-To"] == "suporte@suaempresa.com.br"
    assert "NOVA - Suporte" in m["From"] and "nova@gmail.com" in m["From"]
