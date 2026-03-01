"""OIDC authentication router for SSO login."""
import secrets
import time
from urllib.parse import urlencode, quote

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.jwt import create_tokens
from app.oidc import (
    is_oidc_enabled,
    get_oidc_public_config,
    fetch_openid_configuration,
    create_oauth_client,
    _get_oidc_value,
)

logger = structlog.get_logger(__name__)

ALLOWED_SCHEMES = {"https", "http"}


def _build_external_url(request: Request, db: Session, path: str) -> str:
    """Build an external URL from the request, validated against the configured
    redirect_uri when available. Falls back to X-Forwarded-* headers only if
    the resulting host is on the same domain as the OIDC issuer."""
    from urllib.parse import urlparse

    configured = _get_oidc_value(db, "oidc_redirect_uri")
    if configured:
        parsed = urlparse(configured)
        return f"{parsed.scheme}://{parsed.netloc}{path}"

    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc))

    if scheme not in ALLOWED_SCHEMES:
        scheme = "https"

    issuer = _get_oidc_value(db, "oidc_issuer_url") or ""
    issuer_domain = urlparse(issuer).netloc.split(":")[0] if issuer else ""
    request_domain = host.split(":")[0]

    if issuer_domain:
        issuer_root = ".".join(issuer_domain.rsplit(".", 2)[-2:])
        request_root = ".".join(request_domain.rsplit(".", 2)[-2:])
        if issuer_root != request_root:
            logger.warning(
                "oidc_host_header_mismatch",
                request_host=request_domain,
                issuer_domain=issuer_domain,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Request host does not match OIDC issuer domain",
            )

    return f"{scheme}://{host}{path}"


def _js_string(value: str) -> str:
    """Safely encode a string for embedding in a <script> tag. Uses
    json.dumps for JS-safe quoting, then escapes HTML-sensitive chars
    to prevent breaking out of the script context."""
    import json
    encoded = json.dumps(value)
    return encoded.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")

router = APIRouter(prefix="/api/auth/oidc", tags=["auth"])

STATE_TTL_SECONDS = 600
_state_store: dict[str, dict] = {}


def _cleanup_expired_states():
    """Remove state entries older than the TTL."""
    now = time.time()
    expired = [k for k, v in _state_store.items() if now - v.get("created_at", 0) > STATE_TTL_SECONDS]
    for k in expired:
        _state_store.pop(k, None)


@router.get("/config")
async def oidc_config(db: Session = Depends(get_db)):
    """Public endpoint returning OIDC availability for the login page."""
    return get_oidc_public_config(db)


@router.get("/logout")
async def oidc_logout(request: Request, db: Session = Depends(get_db)):
    """Redirect to the OIDC provider's end-session endpoint."""
    if not is_oidc_enabled(db):
        return RedirectResponse(url="/login", status_code=302)

    issuer_url = _get_oidc_value(db, "oidc_issuer_url")
    post_logout_uri = _build_external_url(request, db, "/login")

    try:
        discovery = await fetch_openid_configuration(issuer_url)
        end_session_endpoint = discovery.get("end_session_endpoint")
        if end_session_endpoint:
            params = urlencode({"post_logout_redirect_uri": post_logout_uri})
            logger.info("oidc_logout_redirect", endpoint=end_session_endpoint)
            return RedirectResponse(url=f"{end_session_endpoint}?{params}", status_code=302)
    except Exception as exc:
        logger.warning("oidc_logout_discovery_failed", error=str(exc))

    return RedirectResponse(url="/login", status_code=302)


@router.get("/login")
async def oidc_login(request: Request, db: Session = Depends(get_db)):
    """Redirect the user to the OIDC provider's authorization page."""
    if not is_oidc_enabled(db):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OIDC is not configured",
        )

    issuer_url = _get_oidc_value(db, "oidc_issuer_url")
    client_id = _get_oidc_value(db, "oidc_client_id")
    client_secret = _get_oidc_value(db, "oidc_client_secret")

    redirect_uri = _build_external_url(request, db, "/api/auth/oidc/callback")

    discovery = await fetch_openid_configuration(issuer_url)
    authorization_endpoint = discovery["authorization_endpoint"]

    _cleanup_expired_states()

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)

    _state_store[state] = {
        "nonce": nonce,
        "redirect_uri": redirect_uri,
        "created_at": time.time(),
    }

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "openid profile email",
        "state": state,
        "nonce": nonce,
    }
    auth_url = f"{authorization_endpoint}?{urlencode(params)}"

    logger.info("oidc_login_redirect", auth_url=authorization_endpoint, redirect_uri=redirect_uri)
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/callback")
async def oidc_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
    db: Session = Depends(get_db),
):
    """Handle the OIDC provider callback after user authentication."""
    if error:
        logger.warning("oidc_callback_error", error=error, description=error_description)
        return RedirectResponse(
            url=f"/login?error={quote(error)}&error_description={quote(error_description)}",
            status_code=302,
        )

    if not state or state not in _state_store:
        logger.warning("oidc_callback_invalid_state")
        return RedirectResponse(url="/login?error=invalid_state", status_code=302)

    session_data = _state_store.pop(state)
    redirect_uri = session_data["redirect_uri"]
    expected_nonce = session_data["nonce"]

    issuer_url = _get_oidc_value(db, "oidc_issuer_url")
    client_id = _get_oidc_value(db, "oidc_client_id")
    client_secret = _get_oidc_value(db, "oidc_client_secret")

    if not all([issuer_url, client_id, client_secret]):
        return RedirectResponse(url="/login?error=oidc_not_configured", status_code=302)

    try:
        discovery = await fetch_openid_configuration(issuer_url)
        token_endpoint = discovery["token_endpoint"]
        userinfo_endpoint = discovery.get("userinfo_endpoint")
        jwks_uri = discovery.get("jwks_uri")

        client = create_oauth_client(client_id, client_secret, redirect_uri)
        token_response = await client.fetch_token(
            token_endpoint,
            code=code,
            grant_type="authorization_code",
        )

        id_token_raw = token_response.get("id_token")
        if id_token_raw and jwks_uri:
            from jose import jwt as jose_jwt, JWTError
            import httpx as _httpx
            async with _httpx.AsyncClient() as http:
                jwks_resp = await http.get(jwks_uri, timeout=10.0)
                jwks = jwks_resp.json()
            try:
                id_claims = jose_jwt.decode(
                    id_token_raw,
                    jwks,
                    algorithms=["RS256", "ES256"],
                    audience=client_id,
                    issuer=issuer_url.rstrip("/"),
                    options={"verify_at_hash": False},
                )
                token_nonce = id_claims.get("nonce", "")
                if token_nonce != expected_nonce:
                    logger.warning("oidc_nonce_mismatch", expected=expected_nonce[:8], got=token_nonce[:8])
                    return RedirectResponse(url="/login?error=nonce_mismatch", status_code=302)
            except JWTError as jwt_err:
                logger.warning("oidc_id_token_validation_failed", error=str(jwt_err))
                return RedirectResponse(url="/login?error=id_token_invalid", status_code=302)

        userinfo = {}
        if userinfo_endpoint:
            userinfo = await client.get(userinfo_endpoint)
            userinfo = userinfo.json()

        await client.aclose()
    except Exception as exc:
        logger.error("oidc_token_exchange_failed", error=str(exc))
        return RedirectResponse(url="/login?error=token_exchange_failed", status_code=302)

    import re
    from sqlalchemy.exc import IntegrityError

    sub = userinfo.get("sub", "")
    email = userinfo.get("email", "")
    email_verified = userinfo.get("email_verified", False)
    preferred_username = userinfo.get("preferred_username", email.split("@")[0] if email else "")
    full_name = userinfo.get("name", "")

    if not sub or not email:
        logger.warning("oidc_missing_claims", sub=sub, email=email)
        return RedirectResponse(url="/login?error=missing_claims", status_code=302)

    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email) or len(email) > 320:
        logger.warning("oidc_invalid_email", email=email[:50])
        return RedirectResponse(url="/login?error=invalid_email", status_code=302)

    preferred_username = re.sub(r"[^\w.-]", "_", preferred_username)[:64]
    full_name = full_name[:200]

    user = db.query(User).filter(User.oidc_subject == sub).first()

    if not user and email_verified:
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.oidc_subject = sub
            db.commit()
            logger.info("oidc_linked_existing_user", user_id=user.id, email=email)
    elif not user and not email_verified:
        logger.info("oidc_skip_email_link_unverified", email=email)

    if not user:
        auto_register = (_get_oidc_value(db, "oidc_auto_register") or "true").lower() == "true"
        if not auto_register:
            logger.warning("oidc_auto_register_disabled", email=email)
            return RedirectResponse(url="/login?error=registration_disabled", status_code=302)

        username = preferred_username or f"user_{secrets.token_hex(4)}"
        for attempt in range(3):
            try:
                existing = db.query(User).filter(User.username == username).first()
                if existing:
                    username = f"{preferred_username}_{secrets.token_hex(4)}"

                user = User(
                    email=email,
                    username=username,
                    hashed_password=None,
                    full_name=full_name,
                    oidc_subject=sub,
                    is_active=True,
                    is_admin=False,
                )
                db.add(user)
                db.commit()
                db.refresh(user)
                logger.info("oidc_user_created", user_id=user.id, username=username, email=email)
                break
            except IntegrityError:
                db.rollback()
                user = db.query(User).filter(User.oidc_subject == sub).first()
                if user:
                    break
                if attempt == 2:
                    logger.error("oidc_user_creation_failed_after_retries", email=email)
                    return RedirectResponse(url="/login?error=registration_failed", status_code=302)

    if not user.is_active:
        logger.warning("oidc_user_inactive", user_id=user.id)
        return RedirectResponse(url="/login?error=account_inactive", status_code=302)

    tokens = create_tokens(
        user_id=user.id,
        username=user.username,
        is_admin=user.is_admin,
    )

    logger.info("oidc_login_success", user_id=user.id, username=user.username)

    return HTMLResponse(
        content=f"""<!DOCTYPE html>
<html><head><title>Signing in...</title></head>
<body><script>
localStorage.setItem("accessToken",{_js_string(tokens.access_token)});
localStorage.setItem("refreshToken",{_js_string(tokens.refresh_token)});
window.location.replace("/");
</script><noscript>JavaScript is required to complete sign-in.</noscript></body>
</html>""",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )
