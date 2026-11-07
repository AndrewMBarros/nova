"""Autenticação no Microsoft Graph via MSAL.

delegated: conta de teste (login por código no navegador, uma vez; token fica em cache).
app:       produção (client credentials, sem login interativo).
"""
from __future__ import annotations

import os

import msal

from app.config import Settings

DELEGATED_SCOPES = ["Mail.ReadWrite", "Mail.Send"]
APP_SCOPES = ["https://graph.microsoft.com/.default"]


class GraphAuthError(Exception):
    pass


class GraphAuth:
    def __init__(self, settings: Settings) -> None:
        self.mode = settings.microsoft_auth_mode
        authority = f"https://login.microsoftonline.com/{settings.microsoft_tenant_id}"
        if not settings.microsoft_client_id:
            raise GraphAuthError("MICROSOFT_CLIENT_ID não configurado no .env")

        if self.mode == "app":
            if not settings.microsoft_client_secret:
                raise GraphAuthError("MICROSOFT_CLIENT_SECRET não configurado (modo app)")
            self._app = msal.ConfidentialClientApplication(
                settings.microsoft_client_id,
                client_credential=settings.microsoft_client_secret,
                authority=authority,
            )
            self._cache = None
        elif self.mode == "delegated":
            self._cache_path = settings.token_cache_path
            self._cache = msal.SerializableTokenCache()
            if os.path.exists(self._cache_path):
                with open(self._cache_path, encoding="utf-8") as f:
                    self._cache.deserialize(f.read())
            self._app = msal.PublicClientApplication(
                settings.microsoft_client_id, authority=authority, token_cache=self._cache
            )
        else:
            raise GraphAuthError(f"MICROSOFT_AUTH_MODE inválido: {self.mode}")

    def _save_cache(self) -> None:
        if self._cache is not None and self._cache.has_state_changed:
            with open(self._cache_path, "w", encoding="utf-8") as f:
                f.write(self._cache.serialize())

    def get_token(self) -> str:
        if self.mode == "app":
            result = self._app.acquire_token_for_client(scopes=APP_SCOPES)
        else:
            result = None
            accounts = self._app.get_accounts()
            if accounts:
                result = self._app.acquire_token_silent(DELEGATED_SCOPES, account=accounts[0])
            if not result:
                flow = self._app.initiate_device_flow(scopes=DELEGATED_SCOPES)
                if "user_code" not in flow:
                    raise GraphAuthError(f"Falha ao iniciar login: {flow}")
                print(flow["message"], flush=True)  # instruções: abrir URL e digitar o código
                result = self._app.acquire_token_by_device_flow(flow)
            self._save_cache()

        if "access_token" not in result:
            raise GraphAuthError(result.get("error_description") or str(result))
        return result["access_token"]
