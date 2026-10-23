"""Service layer: every read and write the pages perform.

Pages never contain SQL. Every statement here is static SQL with bound
parameters - no user value is ever interpolated into a query string. Writes
validate their input first and raise :class:`ValidationError` with a
user-facing message so a page can show an inline error instead of a traceback.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime
from typing import Any, Sequence

import pandas as pd

from core.config import (
    BAG_STATUSES,
    CONTAMINANT_TYPES,
    DEFAULT_BAG_STATUS,
    INCIDENT_SEVERITIES,
    THRESHOLD_METRICS,
    WINDOW_OPTIONS,
    DEFAULT_WINDOW_DAYS,
)
from core.db import connect

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """A user-input problem that should be shown inline, not raised."""


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _rows_frame(rows: Sequence[sqlite3.Row]) -> pd.DataFrame:
    return pd.DataFrame([dict(row) for row in rows]) if rows else pd.DataFrame()


def _window_param(window_days: int) -> str:
    """Validated lookback window as a SQLite modifier parameter."""
    try:
        days = int(window_days)
    except (TypeError, ValueError):
        raise ValidationError("Choose a 30, 60 or 90 day window.") from None
    if days not in WINDOW_OPTIONS:
        raise ValidationError("Choose a 30, 60 or 90 day window.")
    return f"-{days} days"


def _parse_day(value: Any, field_label: str, *, allow_future: bool = False) -> str:
    """Validate a date from a form (``date`` objects come from st.date_input)."""
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = date.fromisoformat(value.strip())
        except ValueError:
            raise ValidationError(f"{field_label} must be a valid date.") from None
    else:
        raise ValidationError(f"{field_label} is required.")
    if not allow_future and parsed > date.today():
        raise ValidationError(f"{field_label} cannot be in the future.")
    if parsed.year < 2000:
        raise ValidationError(f"{field_label} looks too far in the past.")
    return parsed.isoformat()


def _require_text(value: Any, field_label: str, *, max_length: int = 200) -> str:
    text = (value or "").strip() if isinstance(value, str) else ""
    if not text:
        raise ValidationError(f"{field_label} is required.")
    if len(text) > max_length:
        raise ValidationError(f"{field_label} must be {max_length} characters or fewer.")
    return text


def _require_int(value: Any, field_label: str, *, minimum: int, maximum: int) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        raise ValidationError(f"{field_label} must be a whole number.") from None
    if number < minimum or number > maximum:
        raise ValidationError(f"{field_label} must be between {minimum} and {maximum}.")
    return number


def _require_float(value: Any, field_label: str, *, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field_label} must be a number.") from None
    if number != number:  # NaN
        raise ValidationError(f"{field_label} must be a number.")
    if number < minimum or number > maximum:
        raise ValidationError(f"{field_label} must be between {minimum:g} and {maximum:g}.")
    return number


# --------------------------------------------------------------------------
# Reference data
# --------------------------------------------------------------------------
def list_grow_rooms() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT id, code, name FROM grow_rooms ORDER BY code").fetchall()
    return [dict(row) for row in rows]


def list_strains() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, name, species, expected_colonisation_days FROM strains ORDER BY name"
        ).fetchall()
    return [dict(row) for row in rows]


# --------------------------------------------------------------------------
# Bags and colonisation
# --------------------------------------------------------------------------
# Static SQL only: every statement below is a literal string and every value is
# a bound parameter. The "latest reading per bag" lookup is written out in full
# in each query so no SQL text is ever assembled from variables.



_BAGS_WITH_LATEST_ALL_SQL = """
    SELECT b.id,
           b.bag_code,
           b.grow_room_id,
           r.code AS room_code,
           r.name AS room_name,
           b.strain_id,
           s.name AS strain_name,
           b.substrate_recipe,
           b.spawned_on,
           b.status,
           lr.colonisation_pct AS latest_pct,
           lr.reading_date     AS latest_reading_date,
           (SELECT COUNT(*) FROM colonisation_readings c WHERE c.bag_id = b.id) AS reading_count
    FROM substrate_bags b
    JOIN grow_rooms r ON r.id = b.grow_room_id
    JOIN strains s ON s.id = b.strain_id
    LEFT JOIN colonisation_readings lr ON lr.id = (
        SELECT c.id FROM colonisation_readings c
        WHERE c.bag_id = b.id
        ORDER BY c.reading_date DESC, c.id DESC
        LIMIT 1
    )
    ORDER BY r.code, b.bag_code
"""

_BAGS_WITH_LATEST_BY_ROOM_SQL = """
    SELECT b.id,
           b.bag_code,
           b.grow_room_id,
           r.code AS room_code,
           r.name AS room_name,
           b.strain_id,
           s.name AS strain_name,
           b.substrate_recipe,
           b.spawned_on,
           b.status,
           lr.colonisation_pct AS latest_pct,
           lr.reading_date     AS latest_reading_date,
           (SELECT COUNT(*) FROM colonisation_readings c WHERE c.bag_id = b.id) AS reading_count
    FROM substrate_bags b
    JOIN grow_rooms r ON r.id = b.grow_room_id
    JOIN strains s ON s.id = b.strain_id
    LEFT JOIN colonisation_readings lr ON lr.id = (
        SELECT c.id FROM colonisation_readings c
        WHERE c.bag_id = b.id
        ORDER BY c.reading_date DESC, c.id DESC
        LIMIT 1
    )
    WHERE b.grow_room_id = ?
    ORDER BY r.code, b.bag_code
"""


def list_bags(grow_room_id: int | None = None) -> pd.DataFrame:
    params: list[Any] = []
    if grow_room_id is None:
        sql = _BAGS_WITH_LATEST_ALL_SQL
    else:
        sql = _BAGS_WITH_LATEST_BY_ROOM_SQL
        params.append(int(grow_room_id))
    with connect() as conn:
        return _rows_frame(conn.execute(sql, params).fetchall())


def bag_readings(bag_id: int) -> pd.DataFrame:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, reading_date, colonisation_pct, notes
            FROM colonisation_readings
            WHERE bag_id = ?
            ORDER BY reading_date, id
            """,
            (int(bag_id),),
        ).fetchall()
    return _rows_frame(rows)


_ROOM_MEAN_SQL = """
    SELECT AVG(lr.colonisation_pct) AS mean_pct
    FROM substrate_bags b
    LEFT JOIN colonisation_readings lr ON lr.id = (
        SELECT c.id FROM colonisation_readings c
        WHERE c.bag_id = b.id
        ORDER BY c.reading_date DESC, c.id DESC
        LIMIT 1
    )
    WHERE lr.colonisation_pct IS NOT NULL
"""

_ROOM_MEAN_BY_ROOM_SQL = """
    SELECT AVG(lr.colonisation_pct) AS mean_pct
    FROM substrate_bags b
    LEFT JOIN colonisation_readings lr ON lr.id = (
        SELECT c.id FROM colonisation_readings c
        WHERE c.bag_id = b.id
        ORDER BY c.reading_date DESC, c.id DESC
        LIMIT 1
    )
    WHERE lr.colonisation_pct IS NOT NULL AND b.grow_room_id = ?
"""


def room_mean_colonisation(grow_room_id: int | None = None) -> float | None:
    params: list[Any] = []
    if grow_room_id is None:
        sql = _ROOM_MEAN_SQL
    else:
        sql = _ROOM_MEAN_BY_ROOM_SQL
        params.append(int(grow_room_id))
    with connect() as conn:
        value = conn.execute(sql, params).fetchone()[0]
    return None if value is None else float(value)


def create_bag(
    *,
    bag_code: str,
    grow_room_id: int,
    strain_id: int,
    substrate_recipe: str,
    spawned_on: Any,
    status: str = DEFAULT_BAG_STATUS,
) -> int:
    code = _require_text(bag_code, "Bag code", max_length=40)
    recipe = _require_text(substrate_recipe, "Substrate recipe", max_length=120)
    if status not in BAG_STATUSES:
        raise ValidationError("Status must be Colonising, Fruiting, Contaminated or Retired.")
    spawned = _parse_day(spawned_on, "Spawned on")
    try:
        room_id = int(grow_room_id)
        strain = int(strain_id)
    except (TypeError, ValueError):
        raise ValidationError("Choose a grow room and a strain.") from None

    with connect() as conn:
        if conn.execute("SELECT 1 FROM grow_rooms WHERE id = ?", (room_id,)).fetchone() is None:
            raise ValidationError("That grow room no longer exists.")
        if conn.execute("SELECT 1 FROM strains WHERE id = ?", (strain,)).fetchone() is None:
            raise ValidationError("That strain no longer exists.")
        try:
            cursor = conn.execute(
                """
                INSERT INTO substrate_bags
                    (bag_code, grow_room_id, strain_id, substrate_recipe, spawned_on, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    code,
                    room_id,
                    strain,
                    recipe,
                    spawned,
                    status,
                    datetime.now().replace(microsecond=0).isoformat(sep=" "),
                ),
            )
        except sqlite3.IntegrityError as error:
            if "bag_code" in str(error):
                raise ValidationError(f"Bag code {code} is already registered.") from None
            logger.exception("could not register bag %s", code)
            raise ValidationError("That bag could not be saved. Check the values and try again.") from None
        return int(cursor.lastrowid)


def add_reading(
    *,
    bag_id: int,
    reading_date: Any,
    colonisation_pct: Any,
    notes: str | None = None,
) -> int:
    try:
        bag = int(bag_id)
    except (TypeError, ValueError):
        raise ValidationError("Choose a bag.") from None
    pct = _require_int(colonisation_pct, "Colonisation percentage", minimum=0, maximum=100)
    reading_day = _parse_day(reading_date, "Reading date")
    note = (notes or "").strip()[:400]

    with connect() as conn:
        if conn.execute("SELECT 1 FROM substrate_bags WHERE id = ?", (bag,)).fetchone() is None:
            raise ValidationError("That bag no longer exists.")
        cursor = conn.execute(
            """
            INSERT INTO colonisation_readings (bag_id, reading_date, colonisation_pct, notes, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (bag, reading_day, pct, note, datetime.now().replace(microsecond=0).isoformat(sep=" ")),
        )
        return int(cursor.lastrowid)


# --------------------------------------------------------------------------
# Flush yields
# --------------------------------------------------------------------------
_FLUSH_LIST_SQL = """
    SELECT f.id,
           f.flush_number,
           f.harvested_on,
           b.bag_code,
           s.name AS strain,
           r.name AS room,
           f.wet_weight_g,
           f.dry_weight_g,
           f.notes
    FROM flush_yields f
    JOIN substrate_bags b ON b.id = f.bag_id
    JOIN strains s ON s.id = b.strain_id
    JOIN grow_rooms r ON r.id = b.grow_room_id
    WHERE f.harvested_on >= date('now', ?)
      AND (? IS NULL OR b.strain_id = ?)
    ORDER BY f.harvested_on DESC, f.flush_number DESC
"""


def list_flush_yields(strain_id: int | None = None, window_days: int = DEFAULT_WINDOW_DAYS) -> pd.DataFrame:
    window = _window_param(window_days)
    strain = None if strain_id is None else int(strain_id)
    with connect() as conn:
        frame = _rows_frame(conn.execute(_FLUSH_LIST_SQL, (window, strain, strain)).fetchall())
    if not frame.empty:
        frame["dry_wet_ratio"] = (frame["dry_weight_g"] / frame["wet_weight_g"]).round(3)
    return frame


def flush_profile_by_number(strain_id: int, window_days: int = DEFAULT_WINDOW_DAYS) -> pd.DataFrame:
    window = _window_param(window_days)
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT f.flush_number,
                   ROUND(AVG(f.wet_weight_g), 1) AS mean_wet_g,
                   ROUND(MIN(f.wet_weight_g), 1) AS min_wet_g,
                   ROUND(MAX(f.wet_weight_g), 1) AS max_wet_g,
                   COUNT(*) AS flushes
            FROM flush_yields f
            JOIN substrate_bags b ON b.id = f.bag_id
            WHERE f.harvested_on >= date('now', ?) AND b.strain_id = ?
            GROUP BY f.flush_number
            ORDER BY f.flush_number
            """,
            (window, int(strain_id)),
        ).fetchall()
    return _rows_frame(rows)


def next_flush_number(bag_id: int) -> int:
    with connect() as conn:
        value = conn.execute(
            "SELECT COALESCE(MAX(flush_number), 0) FROM flush_yields WHERE bag_id = ?",
            (int(bag_id),),
        ).fetchone()[0]
    return int(value) + 1


def record_flush(
    *,
    bag_id: int,
    flush_number: Any,
    harvested_on: Any,
    wet_weight_g: Any,
    dry_weight_g: Any = None,
    notes: str | None = None,
) -> int:
    try:
        bag = int(bag_id)
    except (TypeError, ValueError):
        raise ValidationError("Choose a bag.") from None
    flush = _require_int(flush_number, "Flush number", minimum=1, maximum=20)
    harvested = _parse_day(harvested_on, "Harvest date")
    wet = _require_float(wet_weight_g, "Wet weight", minimum=0.1, maximum=20000.0)
    dry: float | None = None
    if dry_weight_g is not None and not (isinstance(dry_weight_g, str) and not dry_weight_g.strip()):
        dry = _require_float(dry_weight_g, "Dry weight", minimum=0.0, maximum=20000.0)
        if dry > wet:
            raise ValidationError("Dry weight cannot be higher than wet weight.")
    note = (notes or "").strip()[:400]

    with connect() as conn:
        if conn.execute("SELECT 1 FROM substrate_bags WHERE id = ?", (bag,)).fetchone() is None:
            raise ValidationError("That bag no longer exists.")
        cursor = conn.execute(
            """
            INSERT INTO flush_yields
                (bag_id, flush_number, harvested_on, wet_weight_g, dry_weight_g, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bag,
                flush,
                harvested,
                wet,
                dry,
                note,
                datetime.now().replace(microsecond=0).isoformat(sep=" "),
            ),
        )
        return int(cursor.lastrowid)


# --------------------------------------------------------------------------
# Contamination incidents
# --------------------------------------------------------------------------
_INCIDENT_LIST_SQL = """
    SELECT i.id,
           i.incident_date,
           i.grow_room_id,
           r.name AS room,
           b.bag_code AS bag_code,
           i.contaminant_type,
           i.severity,
           i.status,
           i.action_taken,
           i.resolved_on
    FROM contamination_incidents i
    JOIN grow_rooms r ON r.id = i.grow_room_id
    LEFT JOIN substrate_bags b ON b.id = i.bag_id
    WHERE (? IS NULL OR i.grow_room_id = ?)
      AND (? IS NULL OR i.status = ?)
      AND (? IS NULL OR i.contaminant_type = ?)
    ORDER BY CASE WHEN i.status = 'Open' THEN 0 ELSE 1 END, i.incident_date DESC, i.id DESC
"""


def list_incidents(
    grow_room_id: int | None = None,
    status: str | None = None,
    contaminant_type: str | None = None,
) -> pd.DataFrame:
    room = None if grow_room_id is None else int(grow_room_id)
    status_filter = status or None
    type_filter = contaminant_type or None
    params = (room, room, status_filter, status_filter, type_filter, type_filter)
    with connect() as conn:
        return _rows_frame(conn.execute(_INCIDENT_LIST_SQL, params).fetchall())


def incident_type_counts() -> pd.DataFrame:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT contaminant_type,
                   COUNT(*) AS incidents,
                   SUM(CASE WHEN status = 'Open' THEN 1 ELSE 0 END) AS open_incidents,
                   SUM(CASE WHEN severity = 'High' THEN 1 ELSE 0 END) AS high_severity
            FROM contamination_incidents
            GROUP BY contaminant_type
            ORDER BY incidents DESC, contaminant_type
            """
        ).fetchall()
    return _rows_frame(rows)


def incident_stats() -> dict[str, int]:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN status = 'Open' THEN 1 ELSE 0 END) AS open_count,
                   SUM(CASE WHEN status = 'Resolved' THEN 1 ELSE 0 END) AS resolved_count,
                   SUM(CASE WHEN status = 'Open' AND severity = 'High' THEN 1 ELSE 0 END) AS open_high
            FROM contamination_incidents
            """
        ).fetchone()
    return {
        "total": int(row["total"] or 0),
        "open": int(row["open_count"] or 0),
        "resolved": int(row["resolved_count"] or 0),
        "open_high": int(row["open_high"] or 0),
    }


def log_incident(
    *,
    grow_room_id: int,
    incident_date: Any,
    contaminant_type: str,
    severity: str,
    action_taken: str | None = None,
    bag_id: int | None = None,
) -> int:
    incident_day = _parse_day(incident_date, "Incident date")
    contaminant = _require_text(contaminant_type, "Contaminant type", max_length=60)
    if contaminant not in CONTAMINANT_TYPES:
        raise ValidationError("Choose a contaminant type from the list.")
    if severity not in INCIDENT_SEVERITIES:
        raise ValidationError("Severity must be Low, Medium or High.")
    action = (action_taken or "").strip()[:500]
    try:
        room_id = int(grow_room_id)
    except (TypeError, ValueError):
        raise ValidationError("Choose a grow room.") from None

    with connect() as conn:
        if conn.execute("SELECT 1 FROM grow_rooms WHERE id = ?", (room_id,)).fetchone() is None:
            raise ValidationError("That grow room no longer exists.")
        bag: int | None = None
        if bag_id is not None:
            bag = int(bag_id)
            bag_row = conn.execute(
                "SELECT grow_room_id FROM substrate_bags WHERE id = ?", (bag,)
            ).fetchone()
            if bag_row is None:
                raise ValidationError("That bag no longer exists.")
            if int(bag_row["grow_room_id"]) != room_id:
                raise ValidationError("That bag belongs to a different grow room.")
        cursor = conn.execute(
            """
            INSERT INTO contamination_incidents
                (grow_room_id, bag_id, incident_date, contaminant_type, severity,
                 status, action_taken, resolved_on, created_at)
            VALUES (?, ?, ?, ?, ?, 'Open', ?, NULL, ?)
            """,
            (
                room_id,
                bag,
                incident_day,
                contaminant,
                severity,
                action,
                datetime.now().replace(microsecond=0).isoformat(sep=" "),
            ),
        )
        return int(cursor.lastrowid)


def resolve_incident(incident_id: int) -> bool:
    today = date.today().isoformat()
    with connect() as conn:
        cursor = conn.execute(
            """
            UPDATE contamination_incidents
            SET status = 'Resolved', resolved_on = ?
            WHERE id = ? AND status = 'Open'
            """,
            (today, int(incident_id)),
        )
        return cursor.rowcount > 0


# --------------------------------------------------------------------------
# Environment thresholds
# --------------------------------------------------------------------------
_THRESHOLD_LIST_SQL = """
    SELECT t.id,
           r.code AS room_code,
           r.name AS room,
           t.metric,
           t.min_value,
           t.max_value,
           t.unit,
           t.updated_at
    FROM environment_thresholds t
    JOIN grow_rooms r ON r.id = t.grow_room_id
    WHERE (? IS NULL OR t.metric = ?)
    ORDER BY r.code, t.metric
"""


def list_thresholds(metric: str | None = None) -> pd.DataFrame:
    metric_filter = metric or None
    with connect() as conn:
        return _rows_frame(conn.execute(_THRESHOLD_LIST_SQL, (metric_filter, metric_filter)).fetchall())


def threshold_summary() -> pd.DataFrame:
    """One row per grow room with its humidity and CO2 min-max range."""
    frame = list_thresholds()
    if frame.empty:
        return pd.DataFrame(columns=["room_code", "room", "humidity", "co2"])
    rooms: list[dict[str, Any]] = []
    for (room_code, room), group in frame.groupby(["room_code", "room"], sort=True):
        entry: dict[str, Any] = {"room_code": room_code, "room": room, "humidity": None, "co2": None}
        for _index, row in group.iterrows():
            label = "humidity" if row["metric"] == "humidity_pct" else "co2"
            entry[label] = f"{row['min_value']:g}\u2013{row['max_value']:g} {row['unit']}"
        rooms.append(entry)
    return pd.DataFrame(rooms, columns=["room_code", "room", "humidity", "co2"])


def update_threshold(threshold_id: int, min_value: Any, max_value: Any) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT t.id, t.metric, t.min_value, t.max_value, t.unit, t.grow_room_id, r.name AS room
            FROM environment_thresholds t
            JOIN grow_rooms r ON r.id = t.grow_room_id
            WHERE t.id = ?
            """,
            (int(threshold_id),),
        ).fetchone()
        if row is None:
            raise ValidationError("That threshold row no longer exists.")

        metric = row["metric"]
        bounds = next((entry for entry in THRESHOLD_METRICS if entry[0] == metric), None)
        if bounds is None:
            raise ValidationError("Unknown threshold metric.")
        _key, label, _unit, lower, upper = bounds
        minimum = _require_float(min_value, f"{label} minimum", minimum=lower, maximum=upper)
        maximum = _require_float(max_value, f"{label} maximum", minimum=lower, maximum=upper)
        if not minimum < maximum:
            raise ValidationError(f"{label} minimum must be below its maximum.")

        updated_at = datetime.now().replace(microsecond=0).isoformat(sep=" ")
        conn.execute(
            """
            UPDATE environment_thresholds
            SET min_value = ?, max_value = ?, updated_at = ?
            WHERE id = ?
            """,
            (minimum, maximum, updated_at, int(threshold_id)),
        )
        return {
            "id": int(row["id"]),
            "room": row["room"],
            "metric": metric,
            "min_value": minimum,
            "max_value": maximum,
            "unit": row["unit"],
            "updated_at": updated_at,
        }


# --------------------------------------------------------------------------
# Dashboard aggregates
# --------------------------------------------------------------------------
def overview_kpis(window_days: int = DEFAULT_WINDOW_DAYS) -> dict[str, Any]:
    window = _window_param(window_days)
    previous_from = f"-{int(window_days) * 2} days"
    with connect() as conn:
        colonising = conn.execute(
            "SELECT COUNT(*) FROM substrate_bags WHERE status = 'Colonising'"
        ).fetchone()[0]
        total_bags = conn.execute("SELECT COUNT(*) FROM substrate_bags").fetchone()[0]
        mean_row = conn.execute(
            """
            SELECT AVG(lr.colonisation_pct) AS mean_pct,
                   COUNT(lr.id) AS bags_with_readings
            FROM substrate_bags b
            LEFT JOIN colonisation_readings lr ON lr.id = (
                SELECT c.id FROM colonisation_readings c
                WHERE c.bag_id = b.id
                ORDER BY c.reading_date DESC, c.id DESC
                LIMIT 1
            )
            WHERE lr.colonisation_pct IS NOT NULL
              AND b.status IN ('Colonising','Fruiting')
            """
        ).fetchone()
        wet_window = conn.execute(
            "SELECT COALESCE(SUM(wet_weight_g), 0) FROM flush_yields WHERE harvested_on >= date('now', ?)",
            (window,),
        ).fetchone()[0]
        wet_previous = conn.execute(
            """
            SELECT COALESCE(SUM(wet_weight_g), 0) FROM flush_yields
            WHERE harvested_on >= date('now', ?) AND harvested_on < date('now', ?)
            """,
            (previous_from, window),
        ).fetchone()[0]
        flushes_window = conn.execute(
            "SELECT COUNT(*) FROM flush_yields WHERE harvested_on >= date('now', ?)", (window,)
        ).fetchone()[0]
        open_incidents = conn.execute(
            "SELECT COUNT(*) FROM contamination_incidents WHERE status = 'Open'"
        ).fetchone()[0]
        incidents_window = conn.execute(
            "SELECT COUNT(*) FROM contamination_incidents WHERE incident_date >= date('now', ?)",
            (window,),
        ).fetchone()[0]

    change_pct: float | None = None
    if wet_previous:
        change_pct = round((wet_window - wet_previous) / wet_previous * 100, 1)

    return {
        "colonising_bags": int(colonising),
        "total_bags": int(total_bags),
        "mean_latest_pct": None if mean_row["mean_pct"] is None else round(float(mean_row["mean_pct"]), 1),
        "bags_with_readings": int(mean_row["bags_with_readings"] or 0),
        "wet_yield_g": float(wet_window),
        "wet_yield_previous_g": float(wet_previous),
        "wet_yield_change_pct": change_pct,
        "flushes_in_window": int(flushes_window),
        "open_incidents": int(open_incidents),
        "incidents_in_window": int(incidents_window),
    }


def colonisation_by_room() -> pd.DataFrame:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT r.code AS room_code,
                   r.name AS room,
                   ROUND(AVG(lr.colonisation_pct), 1) AS mean_pct,
                   COUNT(lr.id) AS bags_with_readings
            FROM grow_rooms r
            JOIN substrate_bags b ON b.grow_room_id = r.id
            LEFT JOIN colonisation_readings lr ON lr.id = (
                SELECT c.id FROM colonisation_readings c
                WHERE c.bag_id = b.id
                ORDER BY c.reading_date DESC, c.id DESC
                LIMIT 1
            )
            WHERE lr.colonisation_pct IS NOT NULL
            GROUP BY r.code, r.name
            ORDER BY r.code
            """
        ).fetchall()
    return _rows_frame(rows)


def yield_by_strain(window_days: int = DEFAULT_WINDOW_DAYS) -> pd.DataFrame:
    window = _window_param(window_days)
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT s.name AS strain,
                   ROUND(SUM(f.wet_weight_g), 1) AS wet_g,
                   ROUND(COALESCE(SUM(f.dry_weight_g), 0), 1) AS dry_g,
                   COUNT(*) AS flushes
            FROM flush_yields f
            JOIN substrate_bags b ON b.id = f.bag_id
            JOIN strains s ON s.id = b.strain_id
            WHERE f.harvested_on >= date('now', ?)
            GROUP BY s.name
            ORDER BY wet_g DESC
            """,
            (window,),
        ).fetchall()
    return _rows_frame(rows)


def incidents_by_type(window_days: int = DEFAULT_WINDOW_DAYS) -> pd.DataFrame:
    window = _window_param(window_days)
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT contaminant_type,
                   COUNT(*) AS incidents
            FROM contamination_incidents
            WHERE incident_date >= date('now', ?)
            GROUP BY contaminant_type
            ORDER BY incidents DESC, contaminant_type
            """,
            (window,),
        ).fetchall()
    return _rows_frame(rows)
