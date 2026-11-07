"""Cliente mínimo do Microsoft Graph para a caixa de e-mail da NOVA."""
from __future__ import annotations

import html
import logging
import time
from datetime import datetime

import httpx

from app.config import settings
from app.microsoft.auth import GraphAuth
from app.timeutil import graph_dt

log = logging.getLogger("nova.graph")

GRAPH_URL = "https://graph.microsoft.com/v1.0"
SELECT_FIELDS = (
    "id,internetMessageId,conversationId,subject,from,sender,replyTo,toRecipients,ccRecipients,"
    "receivedDateTime,body,isRead,categories,internetMessageHeaders"
)


class GraphError(Exception):
    pass


def text_to_html(text: str) -> str:
    return html.escape(text).replace("\n", "<br>")


class GraphClient:
    def __init__(self, auth: GraphAuth, mailbox: str | None = None) -> None:
        self.auth = auth
        # delegado: /me ; app: /users/{caixa}
        self.base = f"/users/{mailbox}" if mailbox else "/me"

    def _request(self, method: str, path: str, *, params=None, json=None, headers=None):
        url = f"{GRAPH_URL}{self.base}{path}"
        for attempt in range(4):
            hdrs = {"Authorization": f"Bearer {self.auth.get_token()}", **(headers or {})}
            resp = httpx.request(method, url, params=params, json=json, headers=hdrs, timeout=30)
            if resp.status_code in (429, 503, 504) and attempt < 3:
                wait = float(resp.headers.get("Retry-After", 2 ** attempt))
                log.warning("Graph %s, aguardando %.0fs", resp.status_code, wait)
                time.sleep(wait)
                continue
            if resp.status_code >= 400:
                raise GraphError(f"{method} {path} -> {resp.status_code}: {resp.text[:500]}")
            return resp.json() if resp.content else {}
        raise GraphError(f"{method} {path}: tentativas esgotadas")

    def get_inbox_info(self) -> dict:
        return self._request("GET", "/mailFolders/inbox")

    def list_unread(self, top: int = 25) -> list[dict]:
        data = self._request(
            "GET",
            "/mailFolders/inbox/messages",
            params={"$filter": "isRead eq false", "$select": SELECT_FIELDS, "$top": top},
            headers={"Prefer": 'outlook.body-content-type="text"'},
        )
        messages = data.get("value", [])
        messages.sort(key=lambda m: m.get("receivedDateTime", ""))  # mais antigos primeiro
        return messages

    def list_since(self, since: datetime, top: int = 25) -> list[dict]:
        """E-mails da caixa de entrada recebidos a partir de `since`, do mais antigo ao mais novo.
        Não depende de lido/não lido e não altera nada na caixa."""
        data = self._request(
            "GET",
            "/mailFolders/inbox/messages",
            params={
                "$filter": f"receivedDateTime ge {graph_dt(since)}",
                "$orderby": "receivedDateTime asc",
                "$select": SELECT_FIELDS,
                "$top": top,
            },
            headers={"Prefer": 'outlook.body-content-type="text"'},
        )
        return data.get("value", [])

    def add_category(self, message_id: str, existing: list[str], category: str) -> None:
        if category in existing:
            return
        self._request("PATCH", f"/messages/{message_id}", json={"categories": [*existing, category]})

    def reply(self, message_id: str, html_comment: str) -> None:
        self._request("POST", f"/messages/{message_id}/reply", json={"comment": html_comment})

    def send_mail(self, *, to: str, subject: str, html_body: str) -> None:
        self._request(
            "POST",
            "/sendMail",
            json={
                "message": {
                    "subject": subject,
                    "body": {"contentType": "HTML", "content": html_body},
                    "toRecipients": [{"emailAddress": {"address": to}}],
                },
                "saveToSentItems": True,
            },
        )

    def mark_read(self, message_id: str) -> None:
        self._request("PATCH", f"/messages/{message_id}", json={"isRead": True})


def build_graph_client() -> GraphClient:
    auth = GraphAuth(settings)
    mailbox = None
    if settings.microsoft_auth_mode == "app":
        mailbox = settings.microsoft_mailbox or settings.nova_email
        if not mailbox:
            raise ValueError("Defina MICROSOFT_MAILBOX ou NOVA_EMAIL para o modo app")
    return GraphClient(auth, mailbox)
