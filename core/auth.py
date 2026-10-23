"""Authentication: salted PBKDF2-SHA256 hashes, session helpers, sign-in gate.

The demo credential is the only plaintext password that ever reaches the UI,
and it is still hashed before it is stored. Verification uses
``hmac.compare_digest`` so a wrong password cannot be timed byte by byte.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from typing import Any

import streamlit as st

from core.config import SIGN_IN_PAGE
from core.db import connect

logger = logging.getLogger(__name__)

PBKDF2_ITERATIONS = 260_000
_ALGORITHM = "pbkdf2_sha256"

# Failed sign-in throttling: per browser session, 5 attempts per rolling minute.
MAX_ATTEMPTS = 5
ATTEMPT_WINDOW_SECONDS = 60


def hash_password(password: str, *, salt: str | None = None) -> str:
    """Return ``pbkdf2_sha256$<iterations>$<salt>$<hexdigest>`` for a password."""
    if not isinstance(password, str) or not password:
        raise ValueError("password must be a non-empty string")
    salt_hex = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        PBKDF2_ITERATIONS,
    )
    return f"{_ALGORITHM}${PBKDF2_ITERATIONS}${salt_hex}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Constant-time check of a password against a stored hash."""
    try:
        algorithm, iterations, salt_hex, expected = stored_hash.split("$")
        if algorithm != _ALGORITHM:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return hmac.compare_digest(digest.hex(), expected)


def verify_credentials(identifier: str, password: str) -> dict[str, Any] | None:
    """Look up a user by username or email and verify the password.

    Returns the public user record (never the hash) or ``None``.
    """
    if not identifier or not password:
        return None
    with connect() as conn:
        row = conn.execute(
            """
            SELECT id, username, email, display_name, password_hash
            FROM users
            WHERE lower(username) = lower(?) OR lower(email) = lower(?)
            """,
            (identifier.strip(), identifier.strip()),
        ).fetchone()
    if row is None or not verify_password(password, row["password_hash"]):
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"],
        "display_name": row["display_name"],
    }


# --------------------------------------------------------------------------
# Session state helpers
# --------------------------------------------------------------------------
_SESSION_KEY = "auth_user"


def current_user() -> dict[str, Any] | None:
    user = st.session_state.get(_SESSION_KEY)
    return user if isinstance(user, dict) else None


def sign_in(user: dict[str, Any]) -> None:
    st.session_state[_SESSION_KEY] = user
    st.session_state.pop("sign_in_errors", None)


def sign_out() -> None:
    st.session_state.pop(_SESSION_KEY, None)
    st.session_state.pop("sign_in_errors", None)
    st.session_state.pop("confirm_reset", None)
    st.session_state.pop("login_attempts", None)


def require_login() -> dict[str, Any]:
    """Gate a page: send signed-out visitors back to the sign-in card.

    Streamlit ``pages/`` scripts run even when a visitor types the URL
    directly, so every page calls this before touching data.
    """
    user = current_user()
    if user is not None:
        return user

    st.markdown(
        '<div class="msra-gate">'
        '<div class="msra-gate-title">Sign in required</div>'
        '<p class="msra-gate-body">This page is part of the grow-run workspace. '
        "Returning you to the sign-in card&hellip;</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    try:
        st.switch_page(SIGN_IN_PAGE)
    except Exception:  # pragma: no cover - defensive: navigation should exist
        logger.exception("could not switch to the sign-in page")
        st.error("Please use the sign-in page to continue.")
    st.stop()
    raise RuntimeError("unreachable")  # st.stop() already halts the script


# --------------------------------------------------------------------------
# Sign-in attempt throttling (per session; single-process Streamlit app)
# --------------------------------------------------------------------------
def attempts_remaining() -> int:
    stamps = [t for t in st.session_state.get("login_attempts", []) if time.time() - t < ATTEMPT_WINDOW_SECONDS]
    st.session_state["login_attempts"] = stamps
    return max(MAX_ATTEMPTS - len(stamps), 0)


def record_failed_attempt() -> None:
    stamps = [t for t in st.session_state.get("login_attempts", []) if time.time() - t < ATTEMPT_WINDOW_SECONDS]
    stamps.append(time.time())
    st.session_state["login_attempts"] = stamps


def throttled() -> bool:
    return attempts_remaining() == 0
