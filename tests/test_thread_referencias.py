"""A raiz da conversa não pode mudar depois de várias idas e vindas
(pedido de CNPJ -> CNPJ errado -> CNPJ certo -> "certo"). Para isso, cada
resposta da NOVA leva em References a cadeia acumulada, não só o Message-ID
do e-mail imediatamente anterior; senão o Gmail "reinicia" a thread e o
conversation_id muda, e a NOVA voltaria a pedir o CNPJ já validado.

Este teste simula a troca real de e-mails (via mime.py + parser.py, sem
processor/DB) e confirma que a raiz da thread nunca muda.
"""
from app.email.mime import build_message
from app.email.parser import parse_rfc822


def _bytes(msg) -> bytes:
    return msg.as_bytes()


def test_referencias_preservam_a_raiz_apos_varias_idas_e_vindas():
    # 1) Cliente manda o e-mail original (raiz da conversa).
    original = build_message(sender="cliente@empresa.com", to="nova@suaempresa.com",
                              subject="Sem internet", body="Oi")
    m0 = parse_rfc822(_bytes(original))
    root = m0.conversation_id
    assert root == m0.message_id  # e-mail raiz: conversa = o próprio Message-ID

    # 2) NOVA pede o CNPJ (References = o que m0 trazia [nada] + o Message-ID de m0).
    r1 = build_message(sender="nova@suaempresa.com", to="cliente@empresa.com",
                        subject="Re: Sem internet", body="Informe o CNPJ",
                        in_reply_to=m0.message_id, references=m0.message_id)

    # 3) Cliente responde com o CNPJ ERRADO, citando a resposta da NOVA (r1).
    wrong = build_message(sender="cliente@empresa.com", to="nova@suaempresa.com",
                           subject="Re: Sem internet", body="CNPJ errado")
    wrong["In-Reply-To"] = r1["Message-ID"]
    wrong["References"] = f'{r1["References"]} {r1["Message-ID"]}'
    m1 = parse_rfc822(_bytes(wrong))
    assert m1.conversation_id == root  # ainda aponta pra raiz

    # 4) NOVA pede pra corrigir (References = o que m1 trazia + Message-ID de m1).
    r2_references = f"{m1.headers.get('references', '')} {m1.message_id}".strip()
    r2 = build_message(sender="nova@suaempresa.com", to="cliente@empresa.com",
                        subject="Re: Sem internet", body="CNPJ não confere",
                        in_reply_to=m1.message_id, references=r2_references)

    # 5) Cliente responde com o CNPJ CERTO, citando r2.
    correct = build_message(sender="cliente@empresa.com", to="nova@suaempresa.com",
                             subject="Re: Sem internet", body="CNPJ certo")
    correct["In-Reply-To"] = r2["Message-ID"]
    correct["References"] = f'{r2["References"]} {r2["Message-ID"]}'
    m2 = parse_rfc822(_bytes(correct))
    assert m2.conversation_id == root  # sem a cadeia acumulada, viraria m1.message_id

    # 6) NOVA confirma o atendimento (References = o que m2 trazia + Message-ID de m2).
    r3_references = f"{m2.headers.get('references', '')} {m2.message_id}".strip()
    r3 = build_message(sender="nova@suaempresa.com", to="cliente@empresa.com",
                        subject="Re: Sem internet", body="Atendimento confirmado",
                        in_reply_to=m2.message_id, references=r3_references)

    # 7) Cliente manda "certo", citando r3.
    thanks = build_message(sender="cliente@empresa.com", to="nova@suaempresa.com",
                            subject="Re: Sem internet", body="certo")
    thanks["In-Reply-To"] = r3["Message-ID"]
    thanks["References"] = f'{r3["References"]} {r3["Message-ID"]}'
    m3 = parse_rfc822(_bytes(thanks))
    assert m3.conversation_id == root  # continua a MESMA conversa 3 idas e vindas depois


def test_sem_references_explicito_usa_o_in_reply_to():
    """Sem `references`, o cabeçalho References é igual ao In-Reply-To."""
    m = build_message(sender="nova@x.com", to="c@y.com", subject="s", body="b",
                       in_reply_to="<abc@x.com>")
    assert m["References"] == "<abc@x.com>"
