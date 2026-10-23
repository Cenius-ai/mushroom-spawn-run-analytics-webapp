"""SQLite schema and connection layer.

All statements in this module are static SQL: no user input is ever
interpolated into a query string. Values are bound as parameters.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing, contextmanager
from typing import Iterator

from core.config import DATA_DIR, DB_PATH

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    username      TEXT    NOT NULL UNIQUE,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    display_name  TEXT    NOT NULL,
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS grow_rooms (
    id         INTEGER PRIMARY KEY,
    code       TEXT    NOT NULL UNIQUE,
    name       TEXT    NOT NULL,
    created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS strains (
    id                            INTEGER PRIMARY KEY,
    name                          TEXT    NOT NULL UNIQUE,
    species                       TEXT,
    expected_colonisation_days    INTEGER,
    created_at                    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS substrate_bags (
    id               INTEGER PRIMARY KEY,
    bag_code         TEXT    NOT NULL UNIQUE,
    grow_room_id     INTEGER NOT NULL REFERENCES grow_rooms(id) ON DELETE RESTRICT,
    strain_id        INTEGER NOT NULL REFERENCES strains(id) ON DELETE RESTRICT,
    substrate_recipe TEXT,
    spawned_on       TEXT    NOT NULL,
    status           TEXT    NOT NULL DEFAULT 'Colonising'
                     CHECK (status IN ('Colonising','Fruiting','Contaminated','Retired')),
    created_at       TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_bags_room   ON substrate_bags(grow_room_id);
CREATE INDEX IF NOT EXISTS ix_bags_strain ON substrate_bags(strain_id);
CREATE INDEX IF NOT EXISTS ix_bags_status ON substrate_bags(status);

CREATE TABLE IF NOT EXISTS colonisation_readings (
    id                INTEGER PRIMARY KEY,
    bag_id            INTEGER NOT NULL REFERENCES substrate_bags(id) ON DELETE CASCADE,
    reading_date      TEXT    NOT NULL,
    colonisation_pct  INTEGER NOT NULL CHECK (colonisation_pct BETWEEN 0 AND 100),
    notes             TEXT,
    created_at        TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_readings_bag_date ON colonisation_readings(bag_id, reading_date);

CREATE TABLE IF NOT EXISTS flush_yields (
    id           INTEGER PRIMARY KEY,
    bag_id       INTEGER NOT NULL REFERENCES substrate_bags(id) ON DELETE CASCADE,
    flush_number INTEGER NOT NULL CHECK (flush_number >= 1),
    harvested_on TEXT    NOT NULL,
    wet_weight_g REAL    NOT NULL CHECK (wet_weight_g > 0),
    dry_weight_g REAL             CHECK (dry_weight_g IS NULL OR dry_weight_g >= 0),
    notes        TEXT,
    created_at   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_flush_bag_date ON flush_yields(bag_id, harvested_on);
CREATE INDEX IF NOT EXISTS ix_flush_date     ON flush_yields(harvested_on);

CREATE TABLE IF NOT EXISTS contamination_incidents (
    id               INTEGER PRIMARY KEY,
    grow_room_id     INTEGER NOT NULL REFERENCES grow_rooms(id) ON DELETE RESTRICT,
    bag_id           INTEGER          REFERENCES substrate_bags(id) ON DELETE SET NULL,
    incident_date    TEXT    NOT NULL,
    contaminant_type TEXT    NOT NULL,
    severity         TEXT    NOT NULL CHECK (severity IN ('Low','Medium','High')),
    status           TEXT    NOT NULL DEFAULT 'Open' CHECK (status IN ('Open','Resolved')),
    action_taken     TEXT,
    resolved_on      TEXT,
    created_at       TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_incidents_room   ON contamination_incidents(grow_room_id);
CREATE INDEX IF NOT EXISTS ix_incidents_status ON contamination_incidents(status);
CREATE INDEX IF NOT EXISTS ix_incidents_date   ON contamination_incidents(incident_date);

CREATE TABLE IF NOT EXISTS environment_thresholds (
    id           INTEGER PRIMARY KEY,
    grow_room_id INTEGER NOT NULL REFERENCES grow_rooms(id) ON DELETE CASCADE,
    metric       TEXT    NOT NULL CHECK (metric IN ('humidity_pct','co2_ppm')),
    min_value    REAL    NOT NULL,
    max_value    REAL    NOT NULL CHECK (max_value > min_value),
    unit         TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL,
    UNIQUE (grow_room_id, metric)
);
CREATE INDEX IF NOT EXISTS ix_thresholds_room ON environment_thresholds(grow_room_id);
"""


def connect() -> sqlite3.Connection:
    """Open a connection to the project SQLite file.

    ``check_same_thread=False`` is required because Streamlit executes scripts
    on worker threads; every call opens and closes its own connection so no
    connection is shared across threads for longer than a statement.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    """Transactional connection: commits on success, rolls back on error."""
    conn = connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Create the schema if it does not exist yet (idempotent)."""
    with connection() as conn:
        conn.executescript(SCHEMA_SQL)


# One static statement per table: no table name is ever built into SQL text.
_COUNT_STATEMENTS = (
    ("users", "SELECT COUNT(*) FROM users"),
    ("grow_rooms", "SELECT COUNT(*) FROM grow_rooms"),
    ("strains", "SELECT COUNT(*) FROM strains"),
    ("substrate_bags", "SELECT COUNT(*) FROM substrate_bags"),
    ("colonisation_readings", "SELECT COUNT(*) FROM colonisation_readings"),
    ("flush_yields", "SELECT COUNT(*) FROM flush_yields"),
    ("contamination_incidents", "SELECT COUNT(*) FROM contamination_incidents"),
    ("environment_thresholds", "SELECT COUNT(*) FROM environment_thresholds"),
)


def table_counts() -> dict[str, int]:
    """Row counts per table, used by the seeder and the reset confirmation."""
    with closing(connect()) as conn:
        return {
            table: conn.execute(statement).fetchone()[0]
            for table, statement in _COUNT_STATEMENTS
        }


_ready = False


def ensure_ready() -> None:
    """Schema + demo data on the normal boot path (cheap after the first call)."""
    global _ready
    if _ready:
        return
    init_db()
    from core.seed import ensure_seeded

    ensure_seeded()
    _ready = True


def forget_ready_cache() -> None:
    """Force the next ensure_ready() call to re-check the database."""
    global _ready
    _ready = False
