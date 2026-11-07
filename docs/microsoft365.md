# Microsoft 365 (Microsoft Graph)

For Microsoft 365 / Exchange Online mailboxes, NOVA reads and replies through Microsoft Graph instead
of IMAP/SMTP (basic authentication is being retired there).

1. Register an application in **Microsoft Entra ID** with the `Mail.ReadWrite` and `Mail.Send`
   permissions.
2. Set in `.env`:

   | Variable | Value |
   |---|---|
   | `MAIL_MODE` | `graph_readonly` first, `graph` when ready |
   | `MICROSOFT_CLIENT_ID` | the application (client) ID |
   | `MICROSOFT_TENANT_ID` | your tenant ID (default `common`) |
   | `MICROSOFT_AUTH_MODE` | `delegated` (sign in once with a code in the browser) or `app` (client credentials) |
   | `MICROSOFT_CLIENT_SECRET` | only for `app` mode |
   | `MICROSOFT_MAILBOX` | only for `app` mode: the mailbox to read (defaults to `NOVA_EMAIL`) |

3. Check the connection (read-only): `python -m app.graph_check`

In `delegated` mode the token is cached in `.token_cache.json`, which is git-ignored.

> The `app/microsoft/` modules have not yet been tested against a real Microsoft 365 mailbox.
