"""Teste de conexão com o Microsoft Graph (não altera nada na caixa).

Uso:  python -m app.graph_check
      python -m app.graph_check --send-test seu.outro@email.com
"""
from __future__ import annotations

import argparse

from app.microsoft.graph import build_graph_client


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send-test", metavar="DESTINO")
    args = parser.parse_args()

    graph = build_graph_client()
    inbox = graph.get_inbox_info()
    print(f"Conectado! Caixa de entrada: {inbox.get('totalItemCount')} e-mails, "
          f"{inbox.get('unreadItemCount')} não lidos.")

    for msg in graph.list_unread(top=5):
        sender = ((msg.get("from") or {}).get("emailAddress") or {}).get("address", "?")
        print(f" - {msg.get('receivedDateTime', '')[:16]} | {sender} | {msg.get('subject', '')[:60]}")

    if args.send_test:
        graph.send_mail(to=args.send_test, subject="Teste NOVA",
                        html_body="<p>Teste de envio da NOVA via Microsoft Graph.</p>")
        print(f"E-mail de teste enviado para {args.send_test}.")


if __name__ == "__main__":
    main()
