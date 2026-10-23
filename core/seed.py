"""Deterministic demo dataset: 4 grow rooms, 6 strains, 14 bags, readings,
flush yields, contamination incidents and one humidity + CO2 threshold row per
room. Every date is relative to today so the demo always looks current, and the
generator is seeded so a reset reproduces identical counts (and, on the same
day, identical values).
"""

from __future__ import annotations

import logging
import random
from datetime import date, datetime, timedelta
from typing import Any

from core.auth import hash_password
from core.config import DEMO_CREDENTIALS, SUBSTRATE_RECIPES
from core.db import connection, init_db, table_counts

logger = logging.getLogger(__name__)

SEED = 20240517

GROW_ROOMS = (
    ("GR-A", "Colonisation Bay A"),
    ("GR-B", "Fruiting Chamber B"),
    ("GR-C", "Fruiting Chamber C"),
    ("GR-D", "Spawn Lab D"),
)

STRAINS = (
    ("Blue Oyster", "Pleurotus ostreatus", 18),
    ("Lion's Mane", "Hericium erinaceus", 24),
    ("King Oyster", "Pleurotus eryngii", 21),
    ("Shiitake", "Lentinula edodes", 32),
    ("Reishi", "Ganoderma lucidum", 28),
    ("Golden Enoki", "Flammulina filiformis", 20),
)

# (bag_code, grow room code, strain name, spawned days ago, status, recipe index)
BAGS = (
    ("BAG-2041", "GR-A", "Blue Oyster", 12, "Colonising", 0),
    ("BAG-2042", "GR-A", "Shiitake", 15, "Colonising", 4),
    ("BAG-2043", "GR-A", "Lion's Mane", 18, "Contaminated", 2),
    ("BAG-2044", "GR-B", "Blue Oyster", 34, "Fruiting", 1),
    ("BAG-2045", "GR-B", "King Oyster", 38, "Fruiting", 0),
    ("BAG-2046", "GR-B", "Golden Enoki", 41, "Fruiting", 3),
    ("BAG-2047", "GR-B", "Reishi", 36, "Fruiting", 4),
    ("BAG-2048", "GR-C", "Lion's Mane", 44, "Fruiting", 2),
    ("BAG-2049", "GR-C", "Shiitake", 47, "Fruiting", 0),
    ("BAG-2050", "GR-C", "Blue Oyster", 39, "Retired", 1),
    ("BAG-2051", "GR-C", "King Oyster", 52, "Fruiting", 3),
    ("BAG-2052", "GR-D", "Golden Enoki", 58, "Retired", 0),
    ("BAG-2053", "GR-D", "Lion's Mane", 63, "Retired", 2),
    ("BAG-2054", "GR-D", "Reishi", 20, "Colonising", 4),
)

# Readings per status: colonisation percentage at each sample point.
READING_PROFILE = {
    "Colonising": (20, 38, 57),
    "Fruiting": (22, 48, 76, 100),
    "Retired": (24, 55, 86, 100),
    "Contaminated": (21, 34),
}

# Flushes per status: how many harvests the bag has produced.
FLUSH_PROFILE = {"Fruiting": 3, "Retired": 3}
EXTRA_FLUSH_BAG = "BAG-2048"  # followed through a fourth flush

READING_NOTES = {
    "Colonising": (
        "Mycelium advancing evenly from the spawn point.",
        "First visible hyphal knots, no sour smell.",
        "Bag rotated for even colonisation.",
    ),
    "Fruiting": (
        "Full colonisation confirmed, moved to fruiting conditions.",
        "Pinning across the whole surface.",
        "Primordia count high, air exchange stepped up.",
        "Harvested, then re-hydrated for the next flush.",
    ),
    "Retired": (
        "Colonisation finished ahead of schedule.",
        "Pinset even across the block.",
        "Block compact and clean at retirement.",
        "Retired after final flush, block still firm.",
    ),
    "Contaminated": (
        "Colonisation slowing at the base of the bag.",
        "Off-colour patch flagged for the incident log.",
    ),
}

INCIDENTS = (
    # (room code, bag code or None, days ago, contaminant type, severity, status, action taken)
    ("GR-A", "BAG-2043", 11, "Trichoderma", "High", "Open",
     "Isolated the bag behind the quarantine screen; room fogged and filters swapped."),
    ("GR-B", None, 18, "Penicillium", "Medium", "Resolved",
     "Removed the affected shelf, wiped surfaces with 70% isopropyl and re-sanitised."),
    ("GR-B", "BAG-2045", 24, "Bacterial blotch", "Low", "Resolved",
     "Lowered surface humidity by 4% and increased air exchanges overnight."),
    ("GR-C", None, 9, "Cobweb mould", "Medium", "Open",
     "Shelf quarantined, HEPA unit moved into the chamber and airflow increased."),
    ("GR-C", "BAG-2049", 31, "Trichoderma", "High", "Resolved",
     "Bag double-bagged and removed; surrounding bags inspected and cleared."),
    ("GR-C", None, 44, "Bacillus", "Low", "Resolved",
     "Drainage trays cleaned, standing water removed, humidity cycle adjusted."),
    ("GR-D", "BAG-2052", 16, "Penicillium", "Medium", "Resolved",
     "Casing layer scraped back, culture re-checked and block re-cased."),
    ("GR-D", None, 6, "Aspergillus", "Medium", "Open",
     "Filter wall inspected; room held at the low end of the CO2 range."),
)

# (humidity min, humidity max, co2 min, co2 max) per room, in GROW_ROOMS order.
ROOM_THRESHOLDS = (
    (84.0, 91.0, 420.0, 800.0),
    (86.0, 93.0, 450.0, 850.0),
    (88.0, 95.0, 480.0, 900.0),
    (82.0, 90.0, 400.0, 750.0),
)


# Children before parents so foreign keys never point at a deleted row.
_DELETE_STATEMENTS = (
    "DELETE FROM colonisation_readings",
    "DELETE FROM flush_yields",
    "DELETE FROM contamination_incidents",
    "DELETE FROM environment_thresholds",
    "DELETE FROM substrate_bags",
    "DELETE FROM strains",
    "DELETE FROM grow_rooms",
    "DELETE FROM users",
)


def _iso(day: date) -> str:
    return day.isoformat()


def _timestamp(day: date) -> str:
    return f"{day.isoformat()} 08:30:00"


def _date_span(start: date, end: date, parts: int, offset: float) -> list[date]:
    """Evenly spaced dates inside ``[start, end]`` (never outside it)."""
    span = max((end - start).days, parts)
    return [
        start + timedelta(days=round(span * (index + 1 + offset) / (parts + 1)))
        for index in range(parts)
    ]


def _insert_demo_user(conn) -> int:
    created = datetime.now().replace(microsecond=0).isoformat(sep=" ")
    cursor = conn.execute(
        """
        INSERT INTO users (username, email, password_hash, display_name, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            DEMO_CREDENTIALS["username"],
            DEMO_CREDENTIALS["email"],
            hash_password(DEMO_CREDENTIALS["password"]),
            DEMO_CREDENTIALS["display_name"],
            created,
        ),
    )
    return int(cursor.lastrowid)


def _insert_reference_data(conn) -> tuple[dict[str, int], dict[str, int]]:
    created = datetime.now().replace(microsecond=0).isoformat(sep=" ")
    room_ids: dict[str, int] = {}
    for code, name in GROW_ROOMS:
        cursor = conn.execute(
            "INSERT INTO grow_rooms (code, name, created_at) VALUES (?, ?, ?)",
            (code, name, created),
        )
        room_ids[code] = int(cursor.lastrowid)

    strain_ids: dict[str, int] = {}
    for name, species, expected_days in STRAINS:
        cursor = conn.execute(
            """
            INSERT INTO strains (name, species, expected_colonisation_days, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (name, species, expected_days, created),
        )
        strain_ids[name] = int(cursor.lastrowid)
    return room_ids, strain_ids


def _insert_bags(conn, room_ids: dict[str, int], strain_ids: dict[str, int]) -> dict[str, dict[str, Any]]:
    created = datetime.now().replace(microsecond=0).isoformat(sep=" ")
    today = date.today()
    bags: dict[str, dict[str, Any]] = {}
    for index, (code, room_code, strain_name, spawned_days_ago, status, recipe_index) in enumerate(BAGS):
        room_id = room_ids[room_code]
        strain_id = strain_ids[strain_name]
        if room_id is None or strain_id is None:  # defensive: seed data must resolve
            raise RuntimeError(f"seed row {code} references an unknown room or strain")
        spawned_on = today - timedelta(days=spawned_days_ago)
        cursor = conn.execute(
            """
            INSERT INTO substrate_bags
                (bag_code, grow_room_id, strain_id, substrate_recipe, spawned_on, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                code,
                room_id,
                strain_id,
                SUBSTRATE_RECIPES[recipe_index],
                _iso(spawned_on),
                status,
                created,
            ),
        )
        bags[code] = {
            "id": int(cursor.lastrowid),
            "bag_code": code,
            "room_id": room_id,
            "room_code": room_code,
            "strain_id": strain_id,
            "strain_name": strain_name,
            "spawned_on": spawned_on,
            "status": status,
            "index": index,
        }
    return bags


def _insert_readings(conn, bags: dict[str, dict[str, Any]], rng: random.Random) -> int:
    today = date.today()
    created = datetime.now().replace(microsecond=0).isoformat(sep=" ")
    total = 0
    for bag in bags.values():
        profile = READING_PROFILE[bag["status"]]
        dates = _date_span(bag["spawned_on"], today, len(profile), offset=0.0)
        for position, (reading_day, pct) in enumerate(zip(dates, profile)):
            jitter = rng.randint(-2, 2) if 0 < position < len(profile) - 1 else 0
            value = max(0, min(100, pct + jitter))
            notes = READING_NOTES[bag["status"]][position % len(READING_NOTES[bag["status"]])]
            conn.execute(
                """
                INSERT INTO colonisation_readings
                    (bag_id, reading_date, colonisation_pct, notes, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (bag["id"], _iso(reading_day), value, notes, created),
            )
            total += 1
    return total


def _insert_flushes(conn, bags: dict[str, dict[str, Any]], rng: random.Random) -> int:
    today = date.today()
    created = datetime.now().replace(microsecond=0).isoformat(sep=" ")
    base_weights = (740.0, 495.0, 335.0, 250.0)
    total = 0
    for bag in bags.values():
        if bag["status"] not in FLUSH_PROFILE:
            continue
        count = FLUSH_PROFILE[bag["status"]]
        if bag["bag_code"] == EXTRA_FLUSH_BAG:
            count += 1
        if count <= 0:
            continue
        first_harvest = bag["spawned_on"] + timedelta(days=18)
        harvest_days = _date_span(first_harvest, today, count, offset=0.2)
        for position, harvest_day in enumerate(harvest_days, start=1):
            base = base_weights[min(position - 1, len(base_weights) - 1)]
            wet = round(base * rng.uniform(0.82, 1.18), 1)
            dry = round(wet * rng.uniform(0.09, 0.13), 1)
            note = "First flush, dense cluster." if position == 1 else f"Flush {position}, even pinset."
            conn.execute(
                """
                INSERT INTO flush_yields
                    (bag_id, flush_number, harvested_on, wet_weight_g, dry_weight_g, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (bag["id"], position, _iso(harvest_day), wet, dry, note, created),
            )
            total += 1
    return total


def _insert_incidents(conn, bags: dict[str, dict[str, Any]], room_ids: dict[str, int], rng: random.Random) -> int:
    today = date.today()
    created = datetime.now().replace(microsecond=0).isoformat(sep=" ")
    total = 0
    for room_code, bag_code, days_ago, contaminant, severity, status, action in INCIDENTS:
        bag = bags.get(bag_code) if bag_code else None
        incident_day = today - timedelta(days=days_ago)
        resolved_on = None
        if status == "Resolved":
            resolved_on = _iso(incident_day + timedelta(days=rng.randint(2, 9)))
        conn.execute(
            """
            INSERT INTO contamination_incidents
                (grow_room_id, bag_id, incident_date, contaminant_type, severity,
                 status, action_taken, resolved_on, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                room_ids[room_code],
                bag["id"] if bag else None,
                _iso(incident_day),
                contaminant,
                severity,
                status,
                action,
                resolved_on,
                created,
            ),
        )
        total += 1
    return total


def _insert_thresholds(conn, room_ids: dict[str, int], rng: random.Random) -> int:
    today = date.today()
    total = 0
    for position, (code, _name) in enumerate(GROW_ROOMS):
        room_id = room_ids[code]
        humidity_min, humidity_max, co2_min, co2_max = ROOM_THRESHOLDS[position]
        updated_at = _timestamp(today - timedelta(days=rng.randint(2, 12)))
        for metric, min_value, max_value, unit in (
            ("humidity_pct", humidity_min, humidity_max, "%"),
            ("co2_ppm", co2_min, co2_max, "ppm"),
        ):
            conn.execute(
                """
                INSERT INTO environment_thresholds
                    (grow_room_id, metric, min_value, max_value, unit, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (room_id, metric, float(min_value), float(max_value), unit, updated_at),
            )
            total += 1
    return total


def reset_demo_data() -> dict[str, int]:
    """Wipe and reseed the demo dataset. Idempotent: identical counts every run."""
    init_db()
    rng = random.Random(SEED)
    with connection() as conn:
        # Static statements (children first) - no table name is built into SQL.
        for statement in _DELETE_STATEMENTS:
            conn.execute(statement)

        _insert_demo_user(conn)
        room_ids, strain_ids = _insert_reference_data(conn)
        bags = _insert_bags(conn, room_ids, strain_ids)
        _insert_readings(conn, bags, rng)
        _insert_flushes(conn, bags, rng)
        _insert_incidents(conn, bags, room_ids, rng)
        _insert_thresholds(conn, room_ids, rng)

    counts = table_counts()
    logger.info("demo dataset seeded: %s", counts)
    return counts


def ensure_seeded() -> dict[str, int]:
    """Seed only when the grow rooms table is empty (the boot path)."""
    counts = table_counts()
    if counts.get("grow_rooms", 0) == 0 or counts.get("users", 0) == 0:
        return reset_demo_data()
    return counts
