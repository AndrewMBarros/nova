# Configuration

Everything is read from a `.env` file in the project root. Copy [`.env.example`](../.env.example) and fill
in what you need; anything left out uses the default below.

## Main options

| Variable | Default | Purpose |
|---|---|---|
| `COMPANY_NAME` | `Sua Empresa` | company name shown in messages and in the signature |
| `ENVIRONMENT` | `prod` | `dev` enables the `/dev/*` simulator routes (**local only**, no authentication) |
| `DATABASE_URL` | `sqlite:///./nova.db` | SQLite or `postgresql+psycopg://user:pass@host/db` |
| `MAIL_MODE` | `console` | `console` (simulator), `imap_readonly`, `imap`, `graph_readonly`, `graph` |
| `NOVA_EMAIL` | — | NOVA's own inbox |
| `TEAM_EMAIL` | — | where internal alerts go (customer not found, escalations) |
| `PROCESS_FROM` | first run | date/time cutoff (ISO 8601); nothing before it is ever answered |
| `ONLY_SENDERS` | — | pilot mode: process only these addresses/@domains |
| `TEAM_SENDERS` | — | team addresses/@domains; NOVA never replies to them and steps out of their threads |
| `BLOCKED_SENDERS` / `BLOCKED_SUBJECTS` | — | quick blocklists, comma-separated |
| `MAX_DOCUMENT_REQUESTS` | `2` | how many times NOVA asks for the CNPJ/CPF before escalating |
| `STALE_WAITING_HOURS` | `48` | escalate when the customer doesn't reply (`0` = off) |
| `CONTACT_LINKS_ENABLED` | `true` | remember addresses already validated |
| `LINK_DOMAIN_AUTO` | `false` | also learn the whole domain (never for public providers) |
| `NAME_MATCH_ENABLED` | `true` | identify the customer by the company name in the signature |
| `IGNORE_UNKNOWN_REPLIES` | `true` | ignore replies to threads NOVA never saw |
| `TICKET_TYPE` / `TICKET_CHANNEL` / `TICKET_ACCESS_TYPE` | `Suporte Técnico` / `E-mail` / `Remoto` | fixed values written to every pre-ticket |

Mail credentials (`MAIL_USERNAME`, `MAIL_PASSWORD`, `MICROSOFT_*`) are covered in the
[Gmail](guia-gmail.md) and [Microsoft 365](microsoft365.md) guides. The full list of settings is in
[`app/config.py`](../app/config.py).

## Simulated customer base

Without an ERP, the customer base is a set of plain text files in `data/`. They are reloaded
automatically when saved, with no restart.

| File | Purpose | Format |
|---|---|---|
| `data/clientes.txt` | registered customers | `CNPJ_or_CPF;Name;optional_contacts;optional_aliases` |
| `data/grupos.txt` | people who, in From or Cc, route the email straight to a customer | `CNPJ;email1,email2,@domain` |
| `data/bloqueados.txt` | senders/domains NOVA never replies to | one per line |

Example line in `clientes.txt`, with known contacts (3rd column) and aliases used for name matching
(4th column):

```text
12.345.678/0001-95;Empresa Alpha LTDA;@alpha.com,contador@gmail.com;Alpha,Alpha Telecom
```

## Command-line utilities

```bash
python -m app.manage_customers listar | adicionar "<CNPJ>" "<Name>" | remover "<CNPJ>"
python -m app.manage_links     listar | adicionar "<CNPJ>" "<email or @domain>" | remover "<email or @domain>"
python -m app.manage_blocklist listar | adicionar "@domain.com" | remover "@domain.com"
```

## Running the worker

```bash
python -m app.worker --once      # one cycle, good for testing
python -m app.worker --go-live   # mark "now" as the start: everything already in the inbox is ignored
python -m app.worker             # keep running, polling every POLL_INTERVAL_SECONDS
```

Start with a `*_readonly` mail mode: NOVA reads and decides, but only logs the replies it would send.
