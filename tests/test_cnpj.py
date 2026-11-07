from app.documents.validator import (
    Document, extract_documents, is_valid_cnpj, is_valid_cpf, normalize,
)


def test_cnpj_valido_e_invalido():
    assert is_valid_cnpj("12.345.678/0001-95")
    assert is_valid_cnpj("12345678000195")
    assert not is_valid_cnpj("12.345.678/0001-90")  # dígito errado
    assert not is_valid_cnpj("00.000.000/0000-00")


def test_cpf_valido_e_invalido():
    assert is_valid_cpf("529.982.247-25")
    assert not is_valid_cpf("529.982.247-24")
    assert not is_valid_cpf("111.111.111-11")


def test_cnpj_alfanumerico():
    # gera um CNPJ alfanumérico válido pelo mesmo algoritmo
    from app.documents.validator import _W1, _W2, _cnpj_digit

    base = "AB12CD340001"
    cnpj = base + _cnpj_digit(base, _W1)
    cnpj += _cnpj_digit(cnpj, _W2)
    assert is_valid_cnpj(cnpj)
    assert not is_valid_cnpj(cnpj[:-1] + ("0" if cnpj[-1] != "0" else "1"))


def test_normalize():
    assert normalize("12.345.678/0001-95") == "12345678000195"


def test_extrai_cnpj_do_texto():
    docs = extract_documents("Bom dia.\nCNPJ: 12.345.678/0001-95\nSem internet.")
    assert docs == [Document("CNPJ", "12345678000195")]
    assert docs[0].formatted == "12.345.678/0001-95"


def test_extrai_cnpj_so_numeros():
    assert extract_documents("12345678000195")[0].number == "12345678000195"


def test_extrai_cpf():
    assert extract_documents("Meu CPF é 529.982.247-25")[0].kind == "CPF"


def test_nao_confunde_telefone_ou_protocolo():
    assert extract_documents("Liguem para 21999998888 por favor, estou sem internet desde ontem.") == []
    assert extract_documents("Meu chamado antigo era 123456789012") == []


def test_cnpj_invalido_e_ignorado():
    assert extract_documents("CNPJ 12.345.678/0001-90") == []
