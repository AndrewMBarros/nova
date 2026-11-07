# Privacy (LGPD)

NOVA processes personal data: email addresses, names and message contents, plus customers' CNPJ/CPF.
If you run it with real emails, keep in mind:

- **What is stored.** Message bodies, senders, contact ↔ customer links, pre-tickets and an event log
  per email are stored in the database (`DATABASE_URL`). Restrict access to it and define how long the
  data is kept.
- **Replies to customers.** CPFs are masked (`***.456.789-**`). A customer recognized by their email
  address never gets their own tax ID echoed back; one recognized only by name only sees the name they
  wrote themselves.
- **Alerts to the team.** They include an excerpt of the customer's message, so `TEAM_EMAIL` must be an
  internal mailbox.
- **Development routes.** `/dev/*` exposes emails, links and the customer list without authentication.
  It only exists with `ENVIRONMENT=dev`; never enable it on a server.
- **Credentials.** Mail passwords and Microsoft secrets live only in `.env` (git-ignored), never in code.
- **Legal basis.** Whoever operates NOVA is responsible for the legal basis of the processing and for
  data subjects' rights (access, correction, deletion) under the LGPD.
