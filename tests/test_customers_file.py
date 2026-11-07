from app.customers.service import find_customer, load_customers


def test_carrega_do_arquivo_de_teste(tmp_customers_file):
    customers = load_customers()
    assert customers["12345678000195"] == "Empresa Alpha LTDA"


def test_cliente_cadastrado(tmp_customers_file):
    c = find_customer("12.345.678/0001-95")
    assert c is not None and c.name == "Empresa Alpha LTDA"


def test_cliente_nao_cadastrado(tmp_customers_file):
    assert find_customer("11.222.333/0001-81") is None


def test_ignora_comentarios_e_linhas_vazias(tmp_customers_file):
    assert len(load_customers()) == 3  # as 3 linhas válidas do arquivo de teste
