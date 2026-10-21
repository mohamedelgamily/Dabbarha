import base64
import secrets

import pytest

from app.core.admin_settings import AdminSettings
from app.core.settings import ConfigurationError
from app.services.admin_security import (
    decrypt_totp_secret, encrypt_totp_secret, matching_totp_step, totp_code,
)


def key():
    return base64.b64encode(secrets.token_bytes(32)).decode("ascii")


def test_admin_api_is_off_by_default():
    settings = AdminSettings.from_environ({})
    assert settings.enabled is False
    assert settings.totp_encryption_key == b""


@pytest.mark.parametrize("environment", [
    {"ADMIN_API_ENABLED": "true"},
    {"ADMIN_API_ENABLED": "true", "ADMIN_TOTP_ENCRYPTION_KEY": "placeholder"},
    {"ADMIN_API_ENABLED": "true", "ADMIN_TOTP_ENCRYPTION_KEY": "", "SESSION_AUTH_ENABLED": "true"},
    {"ADMIN_API_ENABLED": "true", "ADMIN_TOTP_ENCRYPTION_KEY": "", "SESSION_AUTH_ENABLED": "true",
     "SESSION_LEGACY_ISSUANCE": "false"},
])
def test_admin_api_enabled_requires_safe_session_and_key(environment):
    with pytest.raises(ConfigurationError):
        AdminSettings.from_environ(environment)


def test_admin_api_requires_durable_sessions_and_disables_legacy_issuance():
    encoded = key()
    base = {"ADMIN_API_ENABLED": "true", "ADMIN_TOTP_ENCRYPTION_KEY": encoded,
            "SESSION_RECEIPT_KEY": key(), "SESSION_AUTH_ENABLED": "true", "SESSION_LEGACY_ISSUANCE": "false"}
    assert AdminSettings.from_environ(base).enabled
    with pytest.raises(ConfigurationError):
        AdminSettings.from_environ(base | {"SESSION_AUTH_ENABLED": "false"})
    with pytest.raises(ConfigurationError):
        AdminSettings.from_environ(base | {"SESSION_LEGACY_ISSUANCE": "true"})
    with pytest.raises(ConfigurationError):
        AdminSettings.from_environ(base | {"ADMIN_TOTP_ENCRYPTION_KEY": base["SESSION_RECEIPT_KEY"]})


def test_totp_replay_window_and_encrypted_factor_material():
    encoded = key()
    encryption_key = base64.b64decode(encoded)
    class Policy:
        totp_encryption_key = encryption_key
        totp_key_id = "test"
    secret = "JBSWY3DPEHPK3PXP"
    step = 600000
    code = totp_code(secret, step)
    assert matching_totp_step(secret, code, step * 30, None) == step
    assert matching_totp_step(secret, code, step * 30, step) is None
    assert matching_totp_step(secret, "not-a-code", step * 30, None) is None
    nonce, ciphertext = encrypt_totp_secret(secret, 77, Policy)
    assert ciphertext != secret.encode("ascii")
    assert decrypt_totp_secret(nonce, ciphertext, 77, Policy) == secret
    with pytest.raises(Exception):
        decrypt_totp_secret(nonce, ciphertext, 78, Policy)
    damaged = ciphertext[:-1] + bytes([ciphertext[-1] ^ 1])
    with pytest.raises(Exception):
        decrypt_totp_secret(nonce, damaged, 77, Policy)


def test_totp_matches_rfc6238_six_digit_sha1_vector():
    # RFC 6238's 59-second vector, truncated to the configured six digits.
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert totp_code(secret, 59 // 30) == "287082"
