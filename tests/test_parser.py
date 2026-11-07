from app.email.parser import clean_body, html_to_text, parse_graph_message


def test_remove_citacao_outlook():
    texto = (
        "CNPJ: 12.345.678/0001-95\n\nContinuamos sem internet.\n\n"
        "De: NOVA <nova@x.com>\nEnviado: sexta-feira, 18 de setembro de 2026 10:00\n"
        "Para: cliente@empresa.com\nAssunto: Re: Internet\n\nOlá, precisamos do CNPJ..."
    )
    assert clean_body(texto) == "CNPJ: 12.345.678/0001-95\n\nContinuamos sem internet."


def test_mantem_linha_de_que_nao_e_cabecalho():
    assert "De: Empresa X" in clean_body("Contrato De: Empresa X\nDe: Empresa X\nSem internet.")


def test_remove_linhas_citadas_e_escreveu():
    texto = "Segue o CNPJ.\n\nEm sex., 18 de set. de 2026 10:00, NOVA escreveu:\n> texto antigo"
    assert clean_body(texto) == "Segue o CNPJ."


def test_html_para_texto():
    assert html_to_text("<p>Olá</p><p>Sem <b>internet</b></p>") == "Olá\n\nSem internet"


def test_parse_mensagem_graph():
    msg = {
        "id": "AAMk123",
        "internetMessageId": "<abc@empresa.com>",
        "conversationId": "conv-1",
        "subject": "Internet fora do ar",
        "from": {"emailAddress": {"name": "João", "address": "Joao@Empresa.com"}},
        "replyTo": [{"emailAddress": {"address": "financeiro@empresa.com"}}],
        "body": {"contentType": "text", "content": "CNPJ 12.345.678/0001-95"},
        "receivedDateTime": "2026-09-19T12:00:00Z",
        "internetMessageHeaders": [
            {"name": "Return-Path", "value": "<joao@empresa.com>"},
            {"name": "Auto-Submitted", "value": "no"},
        ],
    }
    e = parse_graph_message(msg)
    assert e.message_id == "<abc@empresa.com>"
    assert e.from_email == "joao@empresa.com"
    assert e.reply_to == ["financeiro@empresa.com"]
    assert e.conversation_id == "conv-1"
    assert e.return_path == "joao@empresa.com"
    assert e.headers["auto-submitted"] == "no"
