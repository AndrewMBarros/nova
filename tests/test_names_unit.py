"""Lógica pura de comparação de nomes (sem banco)."""
from app.customers.names import candidate_lines, match_customer

C = {"1": "Omega", "2": "Omega Pecas & Acessorios", "3": "Omega Vila Nova", "4": "Omega SÃO JOSÉ",
     "5": "Empresa Alpha LTDA", "6": "Comercial Automotivo LTDA"}


def doc(*lines, aliases=None):
    return match_customer(C, list(lines), aliases).document


def test_nome_do_cadastro_dentro_do_texto():
    assert doc("Omega Comercial Automotivo") == "1"


def test_mais_especifico_vence():
    assert doc("Omega Vila Nova") == "3"
    assert doc("Omega - São José") == "4"


def test_conectores_e_simbolos_sao_ignorados():
    assert doc("Omega Pecas e Acessorios") == "2"
    assert doc("omega pecas & acessorios") == "2"


def test_palavra_so_generica_nao_casa():
    assert doc("Comercial Automotivo") == ""


def test_palavras_de_linhas_diferentes_nao_se_juntam():
    assert doc("Pecas", "Acessorios") == ""


def test_empate_entre_cadastros_e_ambiguo():
    m = match_customer({"1": "ACME Foo", "2": "ACME Foo Ltda"}, ["ACME Foo"])
    assert m.ambiguous == ["1", "2"] and not m.found


def test_apelido():
    assert match_customer({"1": "Razao Social Longa XYZ LTDA"}, ["Omega Auto"], {"1": ["Omega Auto"]}).document == "1"


def test_so_assinatura_e_apresentacao_contam():
    corpo = "Falei com a Omega ontem.\n" + "linha\n" * 8 + "Att"
    assert doc(*candidate_lines(body=corpo)) == ""
    assert doc(*candidate_lines(body="Bom dia, sou da Omega.\n" + "linha\n" * 8 + "Att")) == "1"
