"""Test fixtures: every test runs against a throwaway SQLite file.

MSRA_DB_PATH is set before any core module is imported so the application,
the seeder and the Streamlit AppTest runs all share the same temporary file.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TMP_DIR = Path(tempfile.mkdtemp(prefix="msra-tests-"))
os.environ["MSRA_DB_PATH"] = str(_TMP_DIR / "app.db")
os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")

import pytest  # noqa: E402

from core.db import init_db  # noqa: E402
from core.seed import reset_demo_data  # noqa: E402

DEMO_USER = {
    "id": 1,
    "username": "cenius",
    "email": "cenius@cenius.ai",
    "display_name": "Cenius Demo Operator",
}


@pytest.fixture(scope="session", autouse=True)
def database() -> None:
    init_db()
    reset_demo_data()


@pytest.fixture()
def fresh_data():
    """Guarantee every test starts from the seeded dataset."""
    reset_demo_data()
    return None


@pytest.fixture()
def app_test():
    """Factory for AppTest instances rooted at the repository checkout."""
    from streamlit.testing.v1 import AppTest

    def _build(script: str):
        return AppTest.from_file(str(ROOT / script), default_timeout=30)

    return _build
