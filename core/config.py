"""Application-wide configuration and constants.

Everything here is import-safe: no Streamlit calls, no filesystem writes, no
network access. The database location resolves to a project-relative SQLite
file so a fresh clone boots without any environment configuration.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# A relative SQLite file inside the project keeps a fresh clone bootable.
# MSRA_DB_PATH is optional; when unset the project-relative default wins.
DB_PATH = Path(os.environ.get("MSRA_DB_PATH") or (DATA_DIR / "app.db"))

APP_NAME = "Mushroom Spawn Run Analytics"
APP_SHORT_NAME = "Spawn Run"
APP_TAGLINE = "Colonisation, flush yield and contamination telemetry for the grow suite"

# The one credential the demo signs in with. It is the only plaintext password
# that may ever be rendered in the UI (sign-in card) and it is hashed through
# the same PBKDF2 path as every other account before it touches the database.
DEMO_CREDENTIALS = {
    "email": "cenius@cenius.ai",
    "username": "cenius",
    "password": "cenius",
    "display_name": "Cenius Demo Operator",
}

BAG_STATUSES = ("Colonising", "Fruiting", "Contaminated", "Retired")
DEFAULT_BAG_STATUS = "Colonising"

INCIDENT_SEVERITIES = ("Low", "Medium", "High")
INCIDENT_STATUSES = ("Open", "Resolved")
CONTAMINANT_TYPES = (
    "Trichoderma",
    "Penicillium",
    "Bacterial blotch",
    "Cobweb mould",
    "Bacillus",
    "Aspergillus",
)

THRESHOLD_METRICS = (
    ("humidity_pct", "Humidity", "%", 0.0, 100.0),
    ("co2_ppm", "CO2", "ppm", 0.0, 5000.0),
)
THRESHOLD_METRIC_LABELS = {key: label for key, label, _unit, _lo, _hi in THRESHOLD_METRICS}

WINDOW_OPTIONS = (30, 60, 90)
DEFAULT_WINDOW_DAYS = 90

SUBSTRATE_RECIPES = (
    "Hardwood sawdust + wheat bran 4:1",
    "Straw pellets + soy hull 3:1",
    "Masters mix (hardwood/soy hull) 50:50",
    "Rye grain spawn + coco coir casing",
    "Supplemented oak sawdust, 15% bran",
)

SIGN_IN_PAGE = "streamlit_app.py"
DASHBOARD_PAGE = "pages/1_Dashboard.py"

