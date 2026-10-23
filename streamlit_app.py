"""Mushroom Spawn Run Analytics - sign-in entry point.

This is the app's front door: an unauthenticated visitor gets the sign-in card
with the demo credential printed on it. A signed-in operator is handed straight
to the dashboard.
"""

from __future__ import annotations

import streamlit as st
from streamlit.errors import StreamlitPageNotFoundError

from core import auth, ui
from core.config import APP_NAME, APP_TAGLINE, DASHBOARD_PAGE, DEMO_CREDENTIALS

ui.page_setup("Sign in", "🍄", layout="wide")
ui.bootstrap()

if auth.current_user() is None:
    # The gate comes first: hide the native page navigation until signed in.
    st.markdown(
        "<style>[data-testid='stSidebarNav']{display:none}"
        "[data-testid='stSidebar']{display:none}</style>",
        unsafe_allow_html=True,
    )
else:
    st.switch_page(DASHBOARD_PAGE)
    st.stop()


def _fill_demo_credentials() -> None:
    """One-click demo sign-in: prefill the seeded credential."""
    st.session_state["login_username"] = DEMO_CREDENTIALS["email"]
    st.session_state["login_password"] = DEMO_CREDENTIALS["password"]


errors = st.session_state.get("sign_in_errors") or {}
# A verified-at-submit check is handed to the next run: that run renders the
# submit control disabled with a busy label *while* the credential check runs,
# then either signs in or reports the result.
pending_check = st.session_state.get("sign_in_check")
signing_in = bool(pending_check)

brand_col, card_col = st.columns([1.05, 0.95], gap="large")

with brand_col:
    st.markdown(
        f"""
        <div class="msra-signin-brand">
          <div class="msra-flag"><span class="msra-flag-line" aria-hidden="true"></span>Grow-run workspace</div>
          <h1>{ui._esc(APP_NAME)}</h1>
          <p class="msra-signin-lede">{ui._esc(APP_TAGLINE)}.</p>
          <ul class="msra-signin-points">
            <li><span class="msra-flag-line" aria-hidden="true"></span>
                <span><b>Colonisation readings</b> per substrate bag, room by room,
                with the latest percentage and a trend line for every block.</span></li>
            <li><span class="msra-flag-line" aria-hidden="true"></span>
                <span><b>Flush yields by strain</b> across 30, 60 and 90 day windows,
                wet and dry weights with a dry/wet ratio per harvest.</span></li>
            <li><span class="msra-flag-line" aria-hidden="true"></span>
                <span><b>Contamination log</b> with severity, status and resolution
                dates, plus the humidity and CO2 thresholds each room runs at.</span></li>
          </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

with card_col:
    with st.container(border=True, key="msra-signin-card"):
        st.markdown(
            """
            <div class="msra-card-head">
              <div class="msra-flag"><span class="msra-flag-line" aria-hidden="true"></span>Operator access</div>
              <div class="msra-card-title">Sign in</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.button(
            "Use demo credentials",
            key="demo_fill",
            on_click=_fill_demo_credentials,
            width="stretch",
        )

        # Kept outside the form so toggling it re-renders the password field
        # with its value visible immediately.
        show_password = st.toggle("Show password", key="login_show_password")

        with st.form("sign_in_form", clear_on_submit=False):
            st.text_input(
                "Username or email",
                key="login_username",
                placeholder="cenius@cenius.ai",
                autocomplete="username",
            )
            if errors.get("username"):
                st.markdown(
                    f'<div class="msra-field-error">{ui._esc(errors["username"])}</div>',
                    unsafe_allow_html=True,
                )

            st.text_input(
                "Password",
                key="login_password",
                type="default" if show_password else "password",
                autocomplete="current-password",
                placeholder="••••••",
            )
            if errors.get("password"):
                st.markdown(
                    f'<div class="msra-field-error">{ui._esc(errors["password"])}</div>',
                    unsafe_allow_html=True,
                )

            submitted = st.form_submit_button(
                "Checking credentials…" if signing_in else "Sign in",
                type="primary",
                width="stretch",
                disabled=signing_in,
            )

        st.markdown(
            f"""
            <div class="msra-demo">
              Demo: <span class="msra-demo-code">{ui._esc(DEMO_CREDENTIALS["email"])}</span> /
              <span class="msra-demo-code">{ui._esc(DEMO_CREDENTIALS["password"])}</span>
              &middot; the demo account owns the seeded grow rooms.
            </div>
            """,
            unsafe_allow_html=True,
        )

        sign_in_message = st.session_state.get("sign_in_message")
        if sign_in_message:
            st.error(sign_in_message)

if signing_in:
    # Busy state: the submit control above is already disabled and labelled
    # "Checking credentials…" while this verification runs.
    st.session_state["sign_in_check"] = None
    with st.spinner("Checking credentials…"):
        user = auth.verify_credentials(str(pending_check.get("username", "")), str(pending_check.get("password", "")))
    if user is not None:
        auth.sign_in(user)
        st.success(f"Signed in as {user['display_name']}.")
        try:
            st.switch_page(DASHBOARD_PAGE)
        except StreamlitPageNotFoundError:
            st.info("Signed in. Open the Dashboard from the sidebar.")
        st.stop()
    else:
        auth.record_failed_attempt()
        st.session_state["sign_in_message"] = (
            "Those credentials don't match an account. The demo credential is shown above."
        )
        st.rerun()

if submitted:
    username = str(st.session_state.get("login_username") or "")
    password = str(st.session_state.get("login_password") or "")

    field_errors: dict[str, str] = {}
    if not username.strip():
        field_errors["username"] = "Enter your username or email."
    if not password:
        field_errors["password"] = "Enter your password."

    st.session_state["sign_in_message"] = None
    if field_errors:
        st.session_state["sign_in_errors"] = field_errors
        st.rerun()
    elif auth.throttled():
        st.session_state["sign_in_errors"] = {}
        st.session_state["sign_in_message"] = (
            "Too many sign-in attempts. Wait a minute, then try the demo credential again."
        )
        st.rerun()
    else:
        st.session_state["sign_in_errors"] = {}
        st.session_state["sign_in_check"] = {"username": username, "password": password}
        st.rerun()


st.markdown(
    '<p style="font-size:11.5px;color:var(--muted-foreground);margin-top:18px;">'
    "Local SQLite demo workspace &middot; no outbound network, no external identity provider."
    "</p>",
    unsafe_allow_html=True,
)
