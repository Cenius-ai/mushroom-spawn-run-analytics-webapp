"""Schema constraints and the idempotent demo dataset."""

from __future__ import annotations

import sqlite3

import pytest

from core.db import connect, init_db, table_counts
from core.seed import reset_demo_data

EXPECTED_COUNTS = {
    "users": 1,
    "grow_rooms": 4,
    "strains": 6,
    "substrate_bags": 14,
    "colonisation_readings": 51,
    "flush_yields": 31,
    "contamination_incidents": 8,
    "environment_thresholds": 8,
}


def test_tables_are_created():
    init_db()
    with connect() as conn:
        names = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
    assert {
        "users",
        "grow_rooms",
        "strains",
        "substrate_bags",
        "colonisation_readings",
        "flush_yields",
        "contamination_incidents",
        "environment_thresholds",
    } <= names


def test_seed_counts_and_minimums(fresh_data):
    counts = table_counts()
    assert counts == EXPECTED_COUNTS
    assert counts["colonisation_readings"] >= 40
    assert counts["flush_yields"] >= 30
    # one humidity and one CO2 row for each of the four grow rooms
    with connect() as conn:
        per_room = conn.execute(
            """
            SELECT grow_room_id, COUNT(*) AS rows_per_room,
                   SUM(metric = 'humidity_pct') AS humidity_rows,
                   SUM(metric = 'co2_ppm') AS co2_rows
            FROM environment_thresholds
            GROUP BY grow_room_id
            """
        ).fetchall()
    assert len(per_room) == 4
    for row in per_room:
        assert row["rows_per_room"] == 2
        assert row["humidity_rows"] == 1 and row["co2_rows"] == 1


def test_reset_is_idempotent(fresh_data):
    first = reset_demo_data()
    second = reset_demo_data()
    assert first == second == EXPECTED_COUNTS


def test_bag_status_defaults_to_colonising(fresh_data):
    with connect() as conn:
        room_id = conn.execute("SELECT id FROM grow_rooms ORDER BY code LIMIT 1").fetchone()["id"]
        strain_id = conn.execute("SELECT id FROM strains ORDER BY name LIMIT 1").fetchone()["id"]
        cursor = conn.execute(
            """
            INSERT INTO substrate_bags (bag_code, grow_room_id, strain_id, substrate_recipe,
                                        spawned_on, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("BAG-TEST-DEFAULT", room_id, strain_id, "Test recipe", "2026-01-01", "2026-01-01 00:00:00"),
        )
        inserted = conn.execute(
            "SELECT status FROM substrate_bags WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()["status"]
    assert inserted == "Colonising"


def test_bag_status_check_rejects_unknown_value(fresh_data):
    with connect() as conn:
        room_id = conn.execute("SELECT id FROM grow_rooms ORDER BY code LIMIT 1").fetchone()["id"]
        strain_id = conn.execute("SELECT id FROM strains ORDER BY name LIMIT 1").fetchone()["id"]
    with pytest.raises(sqlite3.IntegrityError):
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO substrate_bags (bag_code, grow_room_id, strain_id, substrate_recipe,
                                            spawned_on, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("BAG-TEST-BAD", room_id, strain_id, "Test recipe", "2026-01-01", "Mouldy", "2026-01-01 00:00:00"),
            )


def test_colonisation_percentage_check(fresh_data):
    with connect() as conn:
        bag_id = conn.execute("SELECT id FROM substrate_bags ORDER BY id LIMIT 1").fetchone()["id"]
    with pytest.raises(sqlite3.IntegrityError):
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO colonisation_readings (bag_id, reading_date, colonisation_pct, notes, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (bag_id, "2026-01-01", 120, None, "2026-01-01 00:00:00"),
            )


def test_threshold_check_requires_max_above_min(fresh_data):
    with connect() as conn:
        room_id = conn.execute("SELECT id FROM grow_rooms ORDER BY code LIMIT 1").fetchone()["id"]
    with pytest.raises(sqlite3.IntegrityError):
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO environment_thresholds (grow_room_id, metric, min_value, max_value, unit, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (room_id, "humidity_pct", 90.0, 60.0, "%", "2026-01-01 00:00:00"),
            )


def test_boot_path_creates_and_seeds_a_missing_database(tmp_path):
    """ensure_ready() (the normal boot path) creates and seeds from nothing."""
    import os
    import subprocess
    import sys

    from conftest import ROOT

    db_file = tmp_path / "fresh" / "app.db"
    env = dict(os.environ)
    env["MSRA_DB_PATH"] = str(db_file)
    code = (
        "import core.db as db; "
        "db.ensure_ready(); "
        "counts = db.table_counts(); "
        "print(counts['users'], counts['grow_rooms'], counts['substrate_bags'], "
        "counts['environment_thresholds'])"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr
    assert db_file.exists()
    assert result.stdout.strip().split() == ["1", "4", "14", "8"]
