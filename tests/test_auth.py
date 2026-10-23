"""Credential storage and verification."""

from __future__ import annotations

import pytest

from core import auth
from core.config import DEMO_CREDENTIALS
from core.db import connect


def test_demo_credentials_verify(fresh_data):
    user = auth.verify_credentials(DEMO_CREDENTIALS["email"], DEMO_CREDENTIALS["password"])
    assert user is not None
    assert user["username"] == "cenius"
    assert user["email"] == "cenius@cenius.ai"

    by_username = auth.verify_credentials("cenius", DEMO_CREDENTIALS["password"])
    assert by_username is not None and by_username["id"] == user["id"]


def test_wrong_password_and_unknown_user_are_rejected(fresh_data):
    assert auth.verify_credentials(DEMO_CREDENTIALS["email"], "not-the-password") is None
    assert auth.verify_credentials("nobody@example.com", "cenius") is None
    assert auth.verify_credentials("", "") is None


def test_password_hash_is_salted_pbkdf2_and_never_plaintext(fresh_data):
    with connect() as conn:
        stored = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?", ("cenius",)
        ).fetchone()["password_hash"]

    assert DEMO_CREDENTIALS["password"] not in stored
    algorithm, iterations, salt, digest = stored.split("$")
    assert algorithm == "pbkdf2_sha256"
    assert int(iterations) >= 200_000
    assert len(salt) == 32 and len(digest) == 64
    assert auth.verify_password(DEMO_CREDENTIALS["password"], stored) is True
    assert auth.verify_password("wrong", stored) is False


def test_hash_is_unique_per_call():
    first = auth.hash_password("same-password")
    second = auth.hash_password("same-password")
    assert first != second  # distinct random salts
    assert auth.verify_password("same-password", first)
    assert auth.verify_password("same-password", second)


@pytest.mark.parametrize("stored", ["", "not-a-hash", "md5$1$aa$bb", "pbkdf2_sha256$x$y$z"])
def test_malformed_hash_never_raises(stored):
    assert auth.verify_password("anything", stored) is False
