"""Step 2 — one-time local user OAuth consent flow.

Run this once (per user) to authorize the GitHub App and store a refresh
token locally, keyed by the GitHub user id. See docs/INITIAL.md Step 2.

Usage:
    python -m broker.consent
"""
from __future__ import annotations

import secrets
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from broker.config import get_config
from broker.token_store import save_refresh_token

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"


class _CallbackHandler(BaseHTTPRequestHandler):
    # Populated by run(); shared across the single expected request.
    expected_state: str = ""
    result: dict = {}

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        parsed = urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return

        params = parse_qs(parsed.query)
        state = params.get("state", [""])[0]
        code = params.get("code", [""])[0]
        error = params.get("error", [""])[0]

        if error:
            self._respond(f"Authorization failed: {error}")
            _CallbackHandler.result = {"error": error}
            return

        if not code or state != _CallbackHandler.expected_state:
            self._respond("Invalid or missing state/code.")
            _CallbackHandler.result = {"error": "invalid_state_or_code"}
            return

        _CallbackHandler.result = {"code": code}
        self._respond("Authorization received. You can close this tab.")

    def _respond(self, message: str) -> None:
        body = message.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        pass  # silence default stderr access logs


def _exchange_code_for_tokens(code: str) -> dict:
    cfg = get_config()
    resp = requests.post(
        TOKEN_URL,
        headers={"Accept": "application/json"},
        data={
            "client_id": cfg.github_client_id,
            "client_secret": cfg.github_client_secret,
            "code": code,
            "redirect_uri": cfg.redirect_uri,
        },
        timeout=10,
    )
    resp.raise_for_status()
    payload = resp.json()
    if "error" in payload:
        raise RuntimeError(f"OAuth token exchange failed: {payload}")
    return payload


def _fetch_user_id(access_token: str) -> str:
    resp = requests.get(
        USER_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return str(resp.json()["id"])


def run() -> None:
    cfg = get_config()
    if not cfg.github_client_id or not cfg.github_client_secret:
        print(
            "GITHUB_APP_CLIENT_ID / GITHUB_APP_CLIENT_SECRET must be set in .env",
            file=sys.stderr,
        )
        raise SystemExit(1)

    state = secrets.token_urlsafe(24)
    _CallbackHandler.expected_state = state
    _CallbackHandler.result = {}

    authorize_url = f"{AUTHORIZE_URL}?" + urlencode(
        {
            "client_id": cfg.github_client_id,
            "redirect_uri": cfg.redirect_uri,
            "state": state,
        }
    )

    print(f"Opening browser for GitHub authorization:\n  {authorize_url}\n")
    webbrowser.open(authorize_url)

    server = HTTPServer((cfg.oauth_callback_host, cfg.oauth_callback_port), _CallbackHandler)
    print(f"Waiting for callback on {cfg.redirect_uri} ...")
    server.handle_request()  # blocks for exactly one request
    server.server_close()

    result = _CallbackHandler.result
    if "error" in result:
        print(f"Authorization failed: {result['error']}", file=sys.stderr)
        raise SystemExit(1)

    tokens = _exchange_code_for_tokens(result["code"])
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        print(
            "No refresh_token in response — ensure the GitHub App has "
            "'Request user authorization (OAuth) during installation' "
            "enabled and issues expiring/refreshable user tokens.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    actor_id = _fetch_user_id(tokens["access_token"])
    save_refresh_token(cfg.refresh_token_store_path, actor_id, refresh_token)

    print(f"Stored refresh token for GitHub user id {actor_id} "
          f"at {cfg.refresh_token_store_path}")
    print("Add this id to ALLOWED_ACTOR_IDS in .env if not already present.")


if __name__ == "__main__":
    run()
