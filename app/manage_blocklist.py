"""Utilitário de linha de comando para data/bloqueados.txt.

Uso:
  python -m app.manage_blocklist listar
  python -m app.manage_blocklist adicionar "@suaempresa.com.br"
  python -m app.manage_blocklist adicionar "alertas@sistema.com.br"
  python -m app.manage_blocklist remover "@suaempresa.com.br"
"""
from __future__ import annotations

import sys

from app.rules.blocklist import _blocklist_path, load_blocked_senders


def listar() -> None:
    itens = load_blocked_senders()
    if not itens:
        print("Nenhum bloqueio cadastrado ainda.")
        return
    for item in itens:
        print(item)
    print(f"\nTotal: {len(itens)}. Arquivo: {_blocklist_path()}")


def adicionar(valor: str) -> None:
    path = _blocklist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{valor.strip().lower()}\n")
    print(f"Adicionado: {valor}")


def remover(valor: str) -> None:
    path = _blocklist_path()
    alvo = valor.strip().lower()
    if not path.exists():
        print("Arquivo ainda não existe.")
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    kept = [ln for ln in lines if ln.strip().startswith("#") or not ln.strip() or ln.strip().lower() != alvo]
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    print(f"Removido (se existia): {valor}")


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] not in ("listar", "adicionar", "remover"):
        print(__doc__)
        return
    if args[0] == "listar":
        listar()
    elif args[0] == "adicionar" and len(args) == 2:
        adicionar(args[1])
    elif args[0] == "remover" and len(args) == 2:
        remover(args[1])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
