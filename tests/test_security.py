from datetime import timedelta

import jwt
import pytest

from app.core.config import JWT_ALGORITHM, JWT_SECRET_KEY
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_password_returns_non_plaintext_hash() -> None:
    password = "correct horse battery staple"

    password_hash = hash_password(password)

    assert isinstance(password_hash, str)
    assert password_hash != password


def test_verify_password_accepts_correct_password() -> None:
    password = "correct horse battery staple"
    password_hash = hash_password(password)

    assert verify_password(password, password_hash) is True


def test_verify_password_rejects_incorrect_password() -> None:
    password_hash = hash_password("correct horse battery staple")

    assert verify_password("wrong password", password_hash) is False


def test_hashing_same_password_twice_produces_valid_hashes() -> None:
    password = "correct horse battery staple"

    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert first_hash != second_hash
    assert verify_password(password, first_hash) is True
    assert verify_password(password, second_hash) is True


def test_create_access_token_creates_decodable_jwt() -> None:
    token = create_access_token(subject="42")

    payload = decode_access_token(token)

    assert payload["sub"] == "42"
    assert "exp" in payload
    assert set(payload.keys()) == {"sub", "exp"}


def test_token_can_be_decoded_with_configured_secret_and_algorithm() -> None:
    token = create_access_token(subject="42")

    payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])

    assert payload["sub"] == "42"
    assert "exp" in payload


def test_expired_token_is_rejected() -> None:
    token = create_access_token(subject="42", expires_delta=timedelta(seconds=-1))

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_tampered_token_is_rejected() -> None:
    token = create_access_token(subject="42")
    header, payload, signature = token.split(".")
    # Alter significant signature bits, not the final base64url padding bits.
    replacement = "A" if signature[0] != "A" else "B"
    tampered_token = f"{header}.{payload}.{replacement}{signature[1:]}"

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(tampered_token)


def test_token_without_expiration_is_rejected() -> None:
    token = jwt.encode({"sub": "42"}, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    with pytest.raises(jwt.MissingRequiredClaimError):
        decode_access_token(token)


def test_old_public_default_cannot_forge_authentication() -> None:
    from datetime import datetime, timezone

    forged = jwt.encode(
        {"sub": "42", "exp": datetime.now(timezone.utc) + timedelta(minutes=60)},
        "development-only-insecure-jwt-secret-change-me",
        algorithm="HS256",
    )
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(forged)


def test_existing_token_shape_with_same_explicit_key_remains_valid() -> None:
    from datetime import datetime, timezone

    previous_format = jwt.encode(
        {"sub": "42", "exp": datetime.now(timezone.utc) + timedelta(minutes=60)},
        JWT_SECRET_KEY,
        algorithm="HS256",
    )
    assert decode_access_token(previous_format)["sub"] == "42"


def test_default_expiration_remains_sixty_minutes() -> None:
    from datetime import datetime, timezone

    before = datetime.now(timezone.utc).timestamp()
    payload = decode_access_token(create_access_token("42"))
    after = datetime.now(timezone.utc).timestamp()
    assert before + 3599 <= payload["exp"] <= after + 3600


def test_deeply_nested_jwt_header_is_a_safe_invalid_token() -> None:
    import base64

    header = '{"alg":"HS256","nested":' + '[' * 1500 + '0' + ']' * 1500 + '}'
    encode = lambda value: base64.urlsafe_b64encode(value.encode()).decode().rstrip('=')
    token = encode(header) + '.' + encode('{"sub":"42","exp":9999999999}') + '.' + encode('x' * 32)
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token)


@pytest.mark.parametrize('malformed', ['not-a-token', 'a.b.c', '..', 'e30.e30.invalid'])
def test_malformed_tokens_raise_safe_jwt_errors(malformed: str) -> None:
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(malformed)
