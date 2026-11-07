# ERP integration

NOVA does not talk to any ERP yet: the customer base is simulated by `data/clientes.txt` and the
pre-ticket is stored in NOVA's own database. The integration point is marked in
[`app/processor.py`](../app/processor.py) with `# >>> INTEGRAÇÃO ERP`.

## What to change

1. **Customer lookup.** Replace the body of `find_customer()` in
   [`app/customers/service.py`](../app/customers/service.py) with a call to the ERP API. It receives a
   normalized CNPJ/CPF and returns a `Customer(document, name)` or `None`. Contact links, name matching
   and group rules all go through this same function, so nothing else has to change.
2. **Opening the ticket.** After `create_pre_atendimento()`, send the `PreAtendimento` record
   ([`app/database/models.py`](../app/database/models.py)) to the ERP and store the ticket number it
   returns.
3. **Confirmation.** Send the confirmation to the customer only after the ticket is created, so a
   failure in the ERP never results in a "we've got it" email for a ticket that doesn't exist.

## Pre-ticket fields

| Field | Content |
|---|---|
| `cliente_documento` / `cliente_nome` | the identified customer |
| `contato_nome` / `contato_email` | who wrote (reply address) |
| `tipo_atendimento` / `canal` / `tipo_acesso` | from `TICKET_TYPE`, `TICKET_CHANNEL`, `TICKET_ACCESS_TYPE` |
| `observacoes` | the original request plus the follow-up that carried the CNPJ; starts with `[CONFIRMAR CLIENTE]` when the customer was identified only by name |

Creating the pre-ticket is idempotent per email, so a retry never opens a duplicate.
