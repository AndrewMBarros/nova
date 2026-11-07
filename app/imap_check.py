"""Teste de conexão IMAP/SMTP (não altera nada na caixa).

Uso:  python -m app.imap_check
      python -m app.imap_check --send-test outro.email@exemplo.com
"""
from __future__ import annotations

import argparse

from app.config import settings
from app.email.sender import SmtpMailGateway
from app.email.sources import ImapSource


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send-test", metavar="DESTINO")
    args = parser.parse_args()

    total, lines = ImapSource(settings).summary(limit=5)
    print(f"Conectado por IMAP! {total} e-mail(s) não lido(s).")
    for line in lines:
        print(" -", line)

    if args.send_test:
        SmtpMailGateway(settings).send_mail(
            to=args.send_test, subject="Teste NOVA", body="Teste de envio da NOVA por SMTP.")
        print(f"E-mail de teste enviado para {args.send_test}.")


if __name__ == "__main__":
    main()
