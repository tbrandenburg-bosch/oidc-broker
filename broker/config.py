"""Shared configuration loader for the OIDC token-broker PoC.

Loads settings from environment variables (populated from `.env` via
python-dotenv at process start). See `.env.example` for the full list.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Config:
    github_app_id: str = os.environ.get("GITHUB_APP_ID", "")
    github_client_id: str = os.environ.get("GITHUB_APP_CLIENT_ID", "")
    github_client_secret: str = os.environ.get("GITHUB_APP_CLIENT_SECRET", "")

    oauth_callback_host: str = os.environ.get("OAUTH_CALLBACK_HOST", "localhost")
    oauth_callback_port: int = int(os.environ.get("OAUTH_CALLBACK_PORT", "8765"))

    broker_host: str = os.environ.get("BROKER_HOST", "localhost")
    broker_port: int = int(os.environ.get("BROKER_PORT", "9000"))

    oidc_issuer: str = os.environ.get(
        "OIDC_ISSUER", "https://token.actions.githubusercontent.com"
    )
    oidc_audience: str = os.environ.get("OIDC_AUDIENCE", "poc-broker")
    expected_repository: str = os.environ.get("EXPECTED_REPOSITORY", "")
    expected_ref: str = os.environ.get("EXPECTED_REF", "")
    allowed_actor_ids: list[str] = field(
        default_factory=lambda: _split_csv(os.environ.get("ALLOWED_ACTOR_IDS", ""))
    )

    refresh_token_store_path: str = os.environ.get(
        "REFRESH_TOKEN_STORE_PATH", "./.data/refresh_tokens.json"
    )

    @property
    def redirect_uri(self) -> str:
        return f"http://{self.oauth_callback_host}:{self.oauth_callback_port}/callback"


def get_config() -> Config:
    return Config()
