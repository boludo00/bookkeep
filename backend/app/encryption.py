"""Fernet encryption for sensitive values stored in app_settings."""
import base64
import os

import structlog
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = structlog.get_logger(__name__)

ENCRYPTED_PREFIX = "enc:"

SENSITIVE_KEYS = {"oidc_client_secret", "hardcover_api_token"}

_SALT = b"bookkeep-settings-encryption-v1"


_secret_key_from_env = bool(os.getenv("BOOKKEEP_SECRET_KEY"))


def _get_fernet() -> Fernet:
    """Derive a Fernet key from BOOKKEEP_SECRET_KEY via PBKDF2."""
    secret = os.getenv("BOOKKEEP_SECRET_KEY", "")
    if not secret:
        from app.jwt import SECRET_KEY
        secret = SECRET_KEY

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        iterations=480_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(secret.encode("utf-8")))
    return Fernet(key)


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string. Returns an 'enc:' prefixed ciphertext."""
    if not plaintext:
        return plaintext
    f = _get_fernet()
    token = f.encrypt(plaintext.encode("utf-8"))
    return ENCRYPTED_PREFIX + token.decode("utf-8")


def decrypt_value(stored: str) -> str:
    """Decrypt a stored value. If not prefixed with 'enc:', returns as-is
    (backward-compatible with existing plaintext values)."""
    if not stored or not stored.startswith(ENCRYPTED_PREFIX):
        return stored
    try:
        f = _get_fernet()
        ciphertext = stored[len(ENCRYPTED_PREFIX):].encode("utf-8")
        return f.decrypt(ciphertext).decode("utf-8")
    except (InvalidToken, Exception) as exc:
        logger.error("decrypt_failed", error=str(exc))
        return ""


def check_encryption_key_stability(db_session):
    """Warn if encrypted values exist but BOOKKEEP_SECRET_KEY is not set,
    which means the encryption key changes on every restart."""
    if _secret_key_from_env:
        return

    from app.models import AppSettings
    for key in SENSITIVE_KEYS:
        setting = db_session.query(AppSettings).filter(AppSettings.key == key).first()
        if setting and setting.value and setting.value.startswith(ENCRYPTED_PREFIX):
            logger.error(
                "BOOKKEEP_SECRET_KEY is not set but encrypted secrets exist in the "
                "database. The encryption key is randomly generated on each restart, "
                "so previously encrypted values will be unrecoverable. Set "
                "BOOKKEEP_SECRET_KEY to a stable value.",
                key=key,
            )
            break


def migrate_plaintext_secrets(db_session) -> int:
    """Encrypt any plaintext sensitive values in app_settings. Idempotent."""
    from app.models import AppSettings

    check_encryption_key_stability(db_session)

    count = 0
    for key in SENSITIVE_KEYS:
        setting = db_session.query(AppSettings).filter(AppSettings.key == key).first()
        if setting and setting.value and not setting.value.startswith(ENCRYPTED_PREFIX):
            setting.value = encrypt_value(setting.value)
            count += 1
            logger.info("encrypted_plaintext_secret", key=key)

    if count > 0:
        db_session.commit()
        logger.info("plaintext_secrets_migrated", count=count)

    return count
