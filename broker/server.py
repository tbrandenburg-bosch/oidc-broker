"""Step 3 — local broker exposing POST /mint.

Verifies a GitHub Actions OIDC JWT, validates PoC-specific claims, exchanges
the caller's stored refresh token for a new user-scoped GitHub access token,
and returns it. See docs/INITIAL.md Step 3.

Run:
    python -m broker.server
"""
from __future__ import annotations

import logging

import jwt
import requests
from flask import Flask, jsonify, request
from jwt import PyJWKClient

from broker.config import get_config
from broker.token_store import get_refresh_token, save_refresh_token

TOKEN_URL = "https://github.com/login/oauth/access_token"

app = Flask(__name__)
log = logging.getLogger("broker")
logging.basicConfig(level=logging.INFO)

_cfg = get_config()
_jwks_client = PyJWKClient(f"{_cfg.oidc_issuer}/.well-known/jwks")


def _verify_oidc_jwt(token: str) -> dict:
    signing_key = _jwks_client.get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=_cfg.oidc_audience,
        issuer=_cfg.oidc_issuer,
    )
    return claims


def _validate_claims(claims: dict) -> str | None:
    """Returns an error message, or None if all claims are valid."""
    if claims.get("repository") != _cfg.expected_repository:
        return "repository claim mismatch"
    if claims.get("ref") != _cfg.expected_ref:
        return "ref claim mismatch"
    actor_id = str(claims.get("actor_id", ""))
    if actor_id not in _cfg.allowed_actor_ids:
        return "actor_id not allow-listed"
    return None


def _exchange_refresh_token(refresh_token: str) -> dict:
    resp = requests.post(
        TOKEN_URL,
        headers={"Accept": "application/json"},
        data={
            "client_id": _cfg.github_client_id,
            "client_secret": _cfg.github_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=10,
    )
    resp.raise_for_status()
    payload = resp.json()
    if "error" in payload:
        raise RuntimeError(f"refresh_token exchange failed: {payload.get('error')}")
    return payload


@app.post("/mint")
def mint():
    body = request.get_json(silent=True) or {}
    oidc_jwt = body.get("jwt")
    if not oidc_jwt:
        return jsonify({"error": "missing 'jwt' in request body"}), 400

    try:
        claims = _verify_oidc_jwt(oidc_jwt)
    except jwt.PyJWTError as exc:
        log.warning("JWT verification failed: %s", exc.__class__.__name__)
        return jsonify({"error": "invalid token"}), 401

    error = _validate_claims(claims)
    if error:
        log.warning("Claim validation failed: %s", error)
        return jsonify({"error": error}), 403

    actor_id = str(claims["actor_id"])
    refresh_token = get_refresh_token(_cfg.refresh_token_store_path, actor_id)
    if not refresh_token:
        log.warning("No stored refresh token for actor_id=%s", actor_id)
        return jsonify({"error": "no stored consent for this user"}), 404

    try:
        tokens = _exchange_refresh_token(refresh_token)
    except (requests.RequestException, RuntimeError) as exc:
        log.error("Refresh token exchange failed: %s", exc.__class__.__name__)
        return jsonify({"error": "token exchange failed"}), 502

    # GitHub rotates refresh tokens on each use — persist the new one.
    new_refresh_token = tokens.get("refresh_token")
    if new_refresh_token:
        save_refresh_token(_cfg.refresh_token_store_path, actor_id, new_refresh_token)

    log.info("Minted token for actor_id=%s (value never logged)", actor_id)
    return jsonify(
        {
            "access_token": tokens["access_token"],
            "expires_in": tokens.get("expires_in"),
            "token_type": tokens.get("token_type", "bearer"),
        }
    )


if __name__ == "__main__":
    missing = [
        name
        for name, value in (
            ("GITHUB_APP_CLIENT_ID", _cfg.github_client_id),
            ("GITHUB_APP_CLIENT_SECRET", _cfg.github_client_secret),
            ("EXPECTED_REPOSITORY", _cfg.expected_repository),
            ("EXPECTED_REF", _cfg.expected_ref),
        )
        if not value
    ]
    if missing:
        raise SystemExit(f"Missing required .env values: {', '.join(missing)}")

    app.run(host=_cfg.broker_host, port=_cfg.broker_port)
