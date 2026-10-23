#!/usr/bin/env bash
# Install project dependencies, create the SQLite schema and seed the demo
# dataset. Runs unprivileged, installs nothing system-wide, prompts for
# nothing, and exits before any server is started.
set -euo pipefail
cd "$(dirname "$0")"

export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_NO_INPUT=1

PYTHON="${PYTHON:-python3}"

echo "==> upgrading packaging tooling"
"$PYTHON" -m pip install --upgrade pip setuptools wheel

echo "==> installing project dependencies"
"$PYTHON" -m pip install -r requirements.txt

echo "==> checking imports"
"$PYTHON" -c "import streamlit, pandas, altair, pytest; import core.config, core.db, core.seed, core.services, core.auth, core.ui"

echo "==> creating schema and seeding demo data"
"$PYTHON" seed.py

echo "==> install complete"
echo "Run the app with:"
echo "  streamlit run streamlit_app.py --server.address=0.0.0.0 --server.port=8501 --server.headless=true"
