"""Utilitário de linha de comando para o arquivo de clientes de teste (data/clientes.txt).

Uso:
  python -m app.manage_customers listar
  python -m app.manage_customers adicionar "12.345.678/0001-95" "Empresa Alpha LTDA"
  python -m app.manage_customers remover "12.345.678/0001-95"
"""
from __future__ import annotations

import sys

from app.customers.service import _customers_path, load_customers
from app.documents.validator import is_valid_cnpj, is_valid_cpf, normalize


def listar() -> None:
    customers = load_customers()
    if not customers:
        print("Nenhum cliente cadastrado ainda.")
        return
    for doc, name in customers.items():
        print(f"{doc} - {name}")
    print(f"\nTotal: {len(customers)} cliente(s). Arquivo: {_customers_path()}")


def adicionar(document: str, name: str) -> None:
    norm = normalize(document)
    if not (is_valid_cnpj(norm) or is_valid_cpf(norm)):
        print(f"Aviso: '{document}' não passou na validação de CNPJ/CPF. Adicionando mesmo assim.")
    path = _customers_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{document};{name}\n")
    print(f"Adicionado: {document} - {name}")


def remover(document: str) -> None:
    path = _customers_path()
    norm = normalize(document)
    if not path.exists():
        print("Arquivo de clientes ainda não existe.")
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    kept = [ln for ln in lines if ln.strip().startswith("#") or not ln.strip()
            or normalize(ln.split(";", 1)[0]) != norm]
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    print(f"Removido (se existia): {document}")


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] not in ("listar", "adicionar", "remover"):
        print(__doc__)
        return
    if args[0] == "listar":
        listar()
    elif args[0] == "adicionar" and len(args) == 3:
        adicionar(args[1], args[2])
    elif args[0] == "remover" and len(args) == 2:
        remover(args[1])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
