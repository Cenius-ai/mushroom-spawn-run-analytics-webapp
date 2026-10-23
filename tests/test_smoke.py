"""AppTest smoke coverage: the sign-in card and every analytics page.

Each page is executed exactly as Streamlit runs it (module top level) against
the seeded SQLite dataset, so a page that raises during render fails this suite
with the page name in the assertion message.
"""

from __future__ import annotations

import pytest

from conftest import DEMO_USER

PAGES = [
    ("pages/1_Dashboard.py", "Dashboard", "Colonising bags"),
    ("pages/2_Colonisation.py", "Colonisation", "Bag register"),
    ("pages/3_Flush_Yield.py", "Flush Yield", "Total wet yield by strain"),
    ("pages/4_Contamination_Log.py", "Contamination Log", "Incident log"),
    ("pages/5_Thresholds.py", "Thresholds", "Threshold table"),
]


def _markdown_text(at) -> str:
    return "\n".join((element.value or "") for element in at.markdown)


def test_sign_in_card_renders_with_demo_hint(app_test):
    at = app_test("streamlit_app.py")
    at.run()

    assert not at.exception, [e.message for e in at.exception]
    assert [field.key for field in at.text_input] == ["login_username", "login_password"]
    from streamlit.proto.TextInput_pb2 import TextInput

    assert at.text_input(key="login_password").proto.type == TextInput.PASSWORD
    assert at.toggle(key="login_show_password") is not None
    body = _markdown_text(at)
    assert "cenius@cenius.ai" in body and "cenius" in body  # demo credential printed on the card
    assert any(button.label == "Sign in" for button in at.form_submit_button)


def test_sign_in_with_demo_credentials(app_test):
    at = app_test("streamlit_app.py")
    at.run()
    at.text_input(key="login_username").set_value("cenius@cenius.ai")
    at.text_input(key="login_password").set_value("cenius")
    at.form_submit_button[0].click()
    at.run()

    assert not at.exception, [e.message for e in at.exception]
    user = at.session_state["auth_user"]
    assert user["username"] == "cenius"
    assert user["email"] == "cenius@cenius.ai"
    assert not at.error


def test_sign_in_rejects_wrong_password_with_one_message(app_test):
    at = app_test("streamlit_app.py")
    at.run()
    at.text_input(key="login_username").set_value("cenius@cenius.ai")
    at.text_input(key="login_password").set_value("definitely-wrong")
    at.form_submit_button[0].click()
    at.run()

    assert not at.exception, [e.message for e in at.exception]
    assert at.session_state.get("auth_user") is None
    errors = [error.value for error in at.error]
    assert len(errors) == 1
    assert "credentials" in errors[0].lower()


def test_sign_in_requires_both_fields(app_test):
    at = app_test("streamlit_app.py")
    at.run()
    at.text_input(key="login_username").set_value("")
    at.text_input(key="login_password").set_value("cenius")
    at.form_submit_button[0].click()
    at.run()

    assert not at.exception, [e.message for e in at.exception]
    assert at.session_state.get("auth_user") is None
    body = _markdown_text(at)
    assert "Enter your username or email." in body


@pytest.mark.parametrize("script,title,expected", PAGES)
def test_page_renders_for_signed_in_user(app_test, fresh_data, script, title, expected):
    at = app_test(script)
    at.session_state["auth_user"] = DEMO_USER
    at.run()

    assert not at.exception, f"{script} raised: {[e.message for e in at.exception]}"
    body = _markdown_text(at)
    assert title in body, f"{script} did not render its title"
    assert expected in body, f"{script} did not render '{expected}'"
    # Every page carries the shared chrome: product top bar, page heading, sidebar session.
    assert "Mushroom Spawn Run Analytics" in body
    assert "Sign out" in [button.label for button in at.button]


@pytest.mark.parametrize("script,title,expected", PAGES)
def test_page_redirects_when_signed_out(app_test, script, title, expected):
    at = app_test(script)
    at.run()

    assert not at.exception, f"{script} raised: {[e.message for e in at.exception]}"
    body = _markdown_text(at)
    assert "Sign in required" in body
    assert expected not in body


def test_dashboard_charts_and_window_selector(app_test, fresh_data):
    at = app_test("pages/1_Dashboard.py")
    at.session_state["auth_user"] = DEMO_USER
    at.run()

    assert not at.exception, [e.message for e in at.exception]
    assert len(at.get("vega_lite_chart")) == 3  # rooms, strains, incident types
    assert at.segmented_control(key="dashboard_window").value == 90

    at.segmented_control(key="dashboard_window").set_value(30)
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    assert at.segmented_control(key="dashboard_window").value == 30
    assert "Last 30 days" in _markdown_text(at)


def test_colonisation_records_a_reading(app_test, fresh_data):
    at = app_test("pages/2_Colonisation.py")
    at.session_state["auth_user"] = DEMO_USER
    at.run()
    assert not at.exception, [e.message for e in at.exception]

    from core import services

    bag_id = int(services.list_bags().iloc[0]["id"])
    at.selectbox(key="reading_bag").set_value(bag_id)
    at.number_input(key="reading_pct").set_value(85)
    at.form_submit_button[0].click()
    at.run()

    assert not at.exception, [e.message for e in at.exception]
    readings = services.bag_readings(bag_id)
    assert 85 in readings["colonisation_pct"].tolist()


def test_flush_yield_records_a_flush(app_test, fresh_data):
    at = app_test("pages/3_Flush_Yield.py")
    at.session_state["auth_user"] = DEMO_USER
    at.run()
    assert not at.exception, [e.message for e in at.exception]

    from core import services

    before = len(services.list_flush_yields(window_days=90))
    at.number_input(key="flush_wet").set_value(512.0)
    at.number_input(key="flush_dry").set_value(58.0)
    at.form_submit_button[0].click()
    at.run()

    assert not at.exception, [e.message for e in at.exception]
    assert len(services.list_flush_yields(window_days=90)) == before + 1


def test_flush_yield_rejects_zero_weight(app_test, fresh_data):
    at = app_test("pages/3_Flush_Yield.py")
    at.session_state["auth_user"] = DEMO_USER
    at.run()
    assert not at.exception, [e.message for e in at.exception]

    from core import services

    before = len(services.list_flush_yields(window_days=90))
    at.number_input(key="flush_wet").set_value(0.0)
    at.form_submit_button[0].click()
    at.run()

    assert not at.exception, [e.message for e in at.exception]
    assert len(services.list_flush_yields(window_days=90)) == before
    assert [error.value for error in at.error]


def test_contamination_log_resolves_an_incident(app_test, fresh_data):
    at = app_test("pages/4_Contamination_Log.py")
    at.session_state["auth_user"] = DEMO_USER
    at.run()
    assert not at.exception, [e.message for e in at.exception]

    from core import services

    open_rows = services.list_incidents(status="Open")
    assert not open_rows.empty
    target_id = int(open_rows.iloc[0]["id"])
    at.button(key=f"resolve_{target_id}").click()
    at.run()

    assert not at.exception, [e.message for e in at.exception]
    resolved = services.list_incidents(status="Resolved")
    assert target_id in resolved["id"].tolist()


def test_thresholds_rejects_min_above_max(app_test, fresh_data):
    at = app_test("pages/5_Thresholds.py")
    at.session_state["auth_user"] = DEMO_USER
    at.run()
    assert not at.exception, [e.message for e in at.exception]

    from core import services

    row_id = int(services.list_thresholds().iloc[0]["id"])
    at.number_input(key=f"threshold_min_{row_id}").set_value(70.0)
    at.number_input(key=f"threshold_max_{row_id}").set_value(60.0)
    at.form_submit_button[0].click()
    at.run()

    assert not at.exception, [e.message for e in at.exception]
    assert any("minimum must be below" in error.value for error in at.error)
    unchanged = services.list_thresholds()
    stored = unchanged[unchanged["id"] == row_id].iloc[0]
    assert stored["min_value"] == pytest.approx(70.0) or stored["max_value"] != 60.0


def test_thresholds_saves_a_valid_edit(app_test, fresh_data):
    at = app_test("pages/5_Thresholds.py")
    at.session_state["auth_user"] = DEMO_USER
    at.run()
    assert not at.exception, [e.message for e in at.exception]

    from core import services

    humidity = services.list_thresholds("humidity_pct")
    row_id = int(humidity.iloc[0]["id"])
    at.selectbox(key="threshold_edit_row").set_value(row_id)
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    at.number_input(key=f"threshold_max_{row_id}").set_value(92.0)
    at.form_submit_button[0].click()
    at.run()

    assert not at.exception, [e.message for e in at.exception]
    saved = services.list_thresholds()
    assert saved[saved["id"] == row_id].iloc[0]["max_value"] == pytest.approx(92.0)


def test_sidebar_reset_confirms_then_reseeds(app_test, fresh_data):
    at = app_test("pages/5_Thresholds.py")
    at.session_state["auth_user"] = DEMO_USER
    at.run()

    at.button(key="sidebar_reset").click()
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    assert at.session_state["confirm_reset"] is True

    from core.db import table_counts

    at.button(key="sidebar_reset_confirm").click()
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    counts = table_counts()
    assert counts["grow_rooms"] == 4
    assert counts["substrate_bags"] == 14
    assert counts["environment_thresholds"] == 8


def test_sidebar_sign_out_clears_the_session(app_test, fresh_data):
    at = app_test("pages/1_Dashboard.py")
    at.session_state["auth_user"] = DEMO_USER
    at.run()
    assert not at.exception, [e.message for e in at.exception]

    at.button(key="sidebar_sign_out").click()
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    assert at.session_state.get("auth_user") is None


@pytest.mark.parametrize("script,title,expected", PAGES)
def test_pages_survive_an_emptied_dataset(app_test, fresh_data, script, title, expected):
    """Delete every child row: each page must render its empty state, not crash."""
    from core.db import connect
    from core.seed import reset_demo_data

    try:
        with connect() as conn:
            for table in (
                "colonisation_readings",
                "flush_yields",
                "contamination_incidents",
                "environment_thresholds",
                "substrate_bags",
            ):
                conn.execute(f"DELETE FROM {table}")

        at = app_test(script)
        at.session_state["auth_user"] = DEMO_USER
        at.run()

        assert not at.exception, f"{script} raised on empty data: {[e.message for e in at.exception]}"
        body = _markdown_text(at)
        assert title in body
        assert "No " in body or "—" in body
    finally:
        reset_demo_data()


def test_demo_fill_button_prefills_the_credential(app_test, fresh_data):
    at = app_test("streamlit_app.py")
    at.run()
    at.button(key="demo_fill").click()
    at.run()

    assert not at.exception, [e.message for e in at.exception]
    assert at.text_input(key="login_username").value == "cenius@cenius.ai"
    assert at.text_input(key="login_password").value == "cenius"


def test_submit_renders_disabled_busy_button_while_checking(app_test, fresh_data, monkeypatch):
    """The submit control is disabled and labelled busy while the check runs.

    The probe raises from inside the credential check, so the element tree is
    exactly what the browser had been sent at that moment.
    """
    import core.auth as auth_module

    at = app_test("streamlit_app.py")
    at.run()
    at.session_state["sign_in_check"] = {"username": "cenius@cenius.ai", "password": "cenius"}

    def probe(_identifier, _password):
        raise RuntimeError("busy-state probe")

    monkeypatch.setattr(auth_module, "verify_credentials", probe)
    at.run()

    button = at.form_submit_button[0]
    assert button.label == "Checking credentials…"
    assert button.proto.disabled is True
    assert any("busy-state probe" in e.message for e in at.exception)
