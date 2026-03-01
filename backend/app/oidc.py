"""OpenID Connect (OIDC) configuration and client setup."""
import os
from typing import Optional

import httpx
import structlog
from authlib.integrations.httpx_client import AsyncOAuth2Client
from sqlalchemy.orm import Session

from app.models import AppSettings
from app.encryption import decrypt_value, SENSITIVE_KEYS

logger = structlog.get_logger(__name__)

OIDC_SETTING_KEYS = [
    "oidc_issuer_url",
    "oidc_client_id",
    "oidc_client_secret",
    "oidc_redirect_uri",
    "oidc_auto_register",
    "oidc_button_text",
]

OIDC_DEFAULTS = {
    "oidc_auto_register": "true",
    "oidc_button_text": "Sign in with SSO",
}


def _get_oidc_value(db: Session, key: str) -> Optional[str]:
    """Get an OIDC setting from env var or database."""
    env_key = key.upper()
    env_value = os.getenv(env_key)
    if env_value:
        return env_value

    setting = db.query(AppSettings).filter(AppSettings.key == key).first()
    if setting and setting.value:
        if key in SENSITIVE_KEYS:
            return decrypt_value(setting.value)
        return setting.value

    return OIDC_DEFAULTS.get(key)


def _get_oidc_source(db: Session, key: str) -> str:
    """Get the source of an OIDC setting (env, ui, or default)."""
    env_key = key.upper()
    if os.getenv(env_key):
        return "env"

    setting = db.query(AppSettings).filter(AppSettings.key == key).first()
    if setting and setting.value:
        return "ui"

    if key in OIDC_DEFAULTS:
        return "default"

    return "none"


def is_oidc_enabled(db: Session) -> bool:
    """Check if OIDC is fully configured (issuer, client_id, client_secret all set)."""
    issuer = _get_oidc_value(db, "oidc_issuer_url")
    client_id = _get_oidc_value(db, "oidc_client_id")
    client_secret = _get_oidc_value(db, "oidc_client_secret")
    return all([issuer, client_id, client_secret])


def get_oidc_settings(db: Session) -> dict:
    """Get all OIDC settings with their sources."""
    settings = {}
    for key in OIDC_SETTING_KEYS:
        value = _get_oidc_value(db, key)
        source = _get_oidc_source(db, key)
        settings[key] = {"value": value, "source": source}
    settings["enabled"] = is_oidc_enabled(db)
    return settings


def get_oidc_public_config(db: Session) -> dict:
    """Get OIDC config safe for the public /config endpoint."""
    enabled = is_oidc_enabled(db)
    return {
        "enabled": enabled,
        "button_text": _get_oidc_value(db, "oidc_button_text") or "Sign in with SSO",
        "logout_url": "/api/auth/oidc/logout" if enabled else None,
    }


async def fetch_openid_configuration(issuer_url: str) -> dict:
    """Fetch the OpenID Connect discovery document from the issuer."""
    well_known_url = issuer_url.rstrip("/") + "/.well-known/openid-configuration"
    async with httpx.AsyncClient() as client:
        response = await client.get(well_known_url, timeout=10.0)
        response.raise_for_status()
        return response.json()


def create_oauth_client(
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> AsyncOAuth2Client:
    """Create an Authlib OAuth2 client for the OIDC flow."""
    return AsyncOAuth2Client(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope="openid profile email",
    )
