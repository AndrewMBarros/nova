from app.rules.blocklist import load_blocked_senders


def test_carrega_lista_de_bloqueio(tmp_blocklist_file):
    itens = load_blocked_senders()
    assert "@suaempresa.com.br" in itens
    assert "alertas@sistema.com.br" in itens


def test_ignora_comentarios(tmp_blocklist_file):
    itens = load_blocked_senders()
    assert len(itens) == 2
