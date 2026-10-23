"""Service-layer queries, aggregates and write validation."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from core import services


def test_overview_kpis_returns_real_numbers(fresh_data):
    kpis = services.overview_kpis(90)
    assert kpis["colonising_bags"] == 3
    assert kpis["total_bags"] == 14
    assert kpis["mean_latest_pct"] is not None and 0 <= kpis["mean_latest_pct"] <= 100
    assert kpis["wet_yield_g"] > 0
    assert kpis["open_incidents"] == 3
    assert kpis["flushes_in_window"] >= 1


def test_aggregates_are_populated(fresh_data):
    by_room = services.colonisation_by_room()
    assert list(by_room.columns) == ["room_code", "room", "mean_pct", "bags_with_readings"]
    assert len(by_room) == 4

    by_strain = services.yield_by_strain(90)
    assert len(by_strain) >= 5
    assert by_strain["wet_g"].is_monotonic_decreasing

    by_type = services.incidents_by_type(90)
    assert len(by_type) == 6
    assert by_type["incidents"].sum() == 8

    summary = services.threshold_summary()
    assert len(summary) == 4
    assert summary["humidity"].notna().all()
    assert summary["co2"].notna().all()


def test_kpi_window_scoping(fresh_data):
    wide = services.overview_kpis(90)
    narrow = services.overview_kpis(30)
    assert narrow["wet_yield_g"] <= wide["wet_yield_g"]
    assert narrow["incidents_in_window"] <= wide["incidents_in_window"]


def test_list_bags_and_readings(fresh_data):
    bags = services.list_bags()
    assert len(bags) == 14
    assert bags["latest_pct"].notna().all()  # every seeded bag has readings

    some_bag = int(bags.iloc[0]["id"])
    readings = services.bag_readings(some_bag)
    assert len(readings) >= 2
    assert readings["colonisation_pct"].between(0, 100).all()

    room_bags = services.list_bags(int(bags.iloc[0]["grow_room_id"]))
    assert (room_bags["grow_room_id"] == bags.iloc[0]["grow_room_id"]).all()


def test_create_bag_and_reject_duplicate(fresh_data):
    rooms = services.list_grow_rooms()
    strains = services.list_strains()
    new_id = services.create_bag(
        bag_code="BAG-9001",
        grow_room_id=rooms[0]["id"],
        strain_id=strains[0]["id"],
        substrate_recipe="Hardwood sawdust + wheat bran 4:1",
        spawned_on=date.today(),
    )
    assert new_id > 0
    created = services.list_bags(rooms[0]["id"])
    row = created[created["bag_code"] == "BAG-9001"].iloc[0]
    assert row["status"] == "Colonising"

    with pytest.raises(services.ValidationError):
        services.create_bag(
            bag_code="BAG-9001",
            grow_room_id=rooms[0]["id"],
            strain_id=strains[0]["id"],
            substrate_recipe="Hardwood sawdust + wheat bran 4:1",
            spawned_on=date.today(),
        )

    with pytest.raises(services.ValidationError):
        services.create_bag(
            bag_code="   ",
            grow_room_id=rooms[0]["id"],
            strain_id=strains[0]["id"],
            substrate_recipe="Hardwood sawdust + wheat bran 4:1",
            spawned_on=date.today(),
        )


def test_add_reading_validates_range_and_updates_latest(fresh_data):
    bags = services.list_bags()
    bag_id = int(bags.iloc[0]["id"])

    with pytest.raises(services.ValidationError):
        services.add_reading(bag_id=bag_id, reading_date=date.today(), colonisation_pct=120)
    with pytest.raises(services.ValidationError):
        services.add_reading(bag_id=bag_id, reading_date=date.today(), colonisation_pct=-1)
    with pytest.raises(services.ValidationError):
        services.add_reading(bag_id=bag_id, reading_date=date.today() + timedelta(days=3), colonisation_pct=50)

    services.add_reading(bag_id=bag_id, reading_date=date.today(), colonisation_pct=85, notes="even flush")
    updated = services.list_bags()
    assert int(updated[updated["id"] == bag_id].iloc[0]["latest_pct"]) == 85


def test_record_flush_validates_and_appears_in_window(fresh_data):
    bags = services.list_bags()
    bag_id = int(bags.iloc[0]["id"])
    before = services.list_flush_yields(window_days=90)

    with pytest.raises(services.ValidationError):
        services.record_flush(bag_id=bag_id, flush_number=1, harvested_on=date.today(), wet_weight_g=0)
    with pytest.raises(services.ValidationError):
        services.record_flush(bag_id=bag_id, flush_number=0, harvested_on=date.today(), wet_weight_g=200)
    with pytest.raises(services.ValidationError):
        services.record_flush(
            bag_id=bag_id, flush_number=1, harvested_on=date.today(), wet_weight_g=100, dry_weight_g=200
        )

    next_number = services.next_flush_number(bag_id)
    services.record_flush(
        bag_id=bag_id,
        flush_number=next_number,
        harvested_on=date.today(),
        wet_weight_g=505.5,
        dry_weight_g=58.0,
        notes="test harvest",
    )
    after = services.list_flush_yields(window_days=90)
    assert len(after) == len(before) + 1
    newest = after.iloc[0]
    assert newest["wet_weight_g"] == pytest.approx(505.5)
    assert newest["dry_wet_ratio"] == pytest.approx(58.0 / 505.5, abs=1e-3)


def test_incident_log_and_resolution(fresh_data):
    rooms = services.list_grow_rooms()
    with pytest.raises(services.ValidationError):
        services.log_incident(
            grow_room_id=rooms[0]["id"],
            incident_date=date.today(),
            contaminant_type="",
            severity="High",
        )
    with pytest.raises(services.ValidationError):
        services.log_incident(
            grow_room_id=rooms[0]["id"],
            incident_date=date.today(),
            contaminant_type="Trichoderma",
            severity="Catastrophic",
        )

    incident_id = services.log_incident(
        grow_room_id=rooms[0]["id"],
        incident_date=date.today(),
        contaminant_type="Trichoderma",
        severity="High",
        action_taken="Quarantined the shelf",
    )
    open_now = services.list_incidents(status="Open")
    created = open_now[open_now["id"] == incident_id].iloc[0]
    assert created["status"] == "Open"
    assert created["resolved_on"] is None

    assert services.resolve_incident(incident_id) is True
    resolved = services.list_incidents(status="Resolved")
    row = resolved[resolved["id"] == incident_id].iloc[0]
    assert row["resolved_on"] == date.today().isoformat()
    assert services.resolve_incident(incident_id) is False  # already resolved


def test_incident_filters(fresh_data):
    all_rows = services.list_incidents()
    assert len(all_rows) == 8
    open_rows = services.list_incidents(status="Open")
    assert len(open_rows) == 3
    assert (open_rows["status"] == "Open").all()

    trichoderma = services.list_incidents(contaminant_type="Trichoderma")
    assert len(trichoderma) == 2
    assert (trichoderma["contaminant_type"] == "Trichoderma").all()

    none_match = services.list_incidents(status="Resolved", contaminant_type="Aspergillus")
    assert none_match.empty


def test_threshold_update_and_validation(fresh_data):
    rows = services.list_thresholds("humidity_pct")
    assert len(rows) == 4
    target = rows.iloc[0]
    threshold_id = int(target["id"])
    original = services.list_thresholds()
    before = original[original["id"] == threshold_id].iloc[0]

    with pytest.raises(services.ValidationError):
        services.update_threshold(threshold_id, min_value=70, max_value=60)

    unchanged = services.list_thresholds()
    after_invalid = unchanged[unchanged["id"] == threshold_id].iloc[0]
    assert after_invalid["min_value"] == before["min_value"]
    assert after_invalid["max_value"] == before["max_value"]

    updated = services.update_threshold(threshold_id, min_value=float(before["min_value"]), max_value=92)
    assert updated["max_value"] == 92
    saved = services.list_thresholds()
    assert saved[saved["id"] == threshold_id].iloc[0]["max_value"] == 92
    assert updated["updated_at"] >= str(before["updated_at"])

    summary = services.threshold_summary()
    assert "92" in " ".join(summary["humidity"].tolist())


def test_threshold_metric_filter(fresh_data):
    assert len(services.list_thresholds()) == 8
    assert len(services.list_thresholds("co2_ppm")) == 4
    assert (services.list_thresholds("co2_ppm")["metric"] == "co2_ppm").all()


def test_invalid_window_is_rejected(fresh_data):
    with pytest.raises(services.ValidationError):
        services.overview_kpis(45)
    with pytest.raises(services.ValidationError):
        services.yield_by_strain("90; drop table flush_yields")
