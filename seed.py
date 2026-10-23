"""Seed entry point: create the schema and the demo dataset, then exit.

Run with ``python3 seed.py`` (idempotent - it never starts the web server and
never prompts). Pass ``--reset`` to wipe and reseed even when data exists.
"""

from __future__ import annotations

import sys

from core.db import init_db
from core.seed import ensure_seeded, reset_demo_data


def main(argv: list[str]) -> int:
    init_db()
    if "--reset" in argv:
        counts = reset_demo_data()
        print("demo data reset")
    else:
        counts = ensure_seeded()
        print("demo data ready")
    for table, count in counts.items():
        print(f"  {table:<24} {count}")
    if counts.get("users", 0) == 0 or counts.get("grow_rooms", 0) == 0:
        print("seed failed: expected at least one user and one grow room", file=sys.stderr)
        return 1
    print("seed complete - start the app with:")
    print("  streamlit run streamlit_app.py --server.address=0.0.0.0 --server.port=8501 --server.headless=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
