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
    replacement = "x" if token[-1] != "x" else "y"
    tampered_token = f"{token[:-1]}{replacement}"

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(tampered_token)


def test_token_without_expiration_is_rejected() -> None:
    token = jwt.encode({"sub": "42"}, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    with pytest.raises(jwt.MissingRequiredClaimError):
        decode_access_token(token)
