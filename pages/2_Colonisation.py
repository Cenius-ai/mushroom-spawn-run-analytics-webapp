"""Substrate bag colonisation: room-scoped bag list, readings and trend."""

from __future__ import annotations

import sqlite3

import altair as alt
import pandas as pd
import streamlit as st

from core import services, ui
from core.config import BAG_STATUSES, DEFAULT_BAG_STATUS, SUBSTRATE_RECIPES

user = ui.signed_in_page("Colonisation", ":material/sensors:", context_label="Bag colonisation")

ui.page_head(
    "Colonisation",
    "Substrate bags and readings",
    "Register bags, record the percentage of colonised substrate and follow each block's trend. "
    "The grow-room filter scopes the bag list, the readings and the trend chart.",
)

try:
    rooms = services.list_grow_rooms()
    strains = services.list_strains()
except sqlite3.Error as exc:
    ui.query_error("grow rooms and strains", exc)
    st.stop()

if not rooms or not strains:
    ui.empty_state(
        "No grow rooms or strains configured",
        "Reset the demo data from the sidebar to restore the seeded grow rooms and strains.",
    )
    st.stop()

filter_col, scope_col = st.columns([0.5, 1.5], gap="medium")
with filter_col:
    room_options = [None] + [room["id"] for room in rooms]
    selected_room_id = st.selectbox(
        "Grow room",
        options=room_options,
        format_func=lambda room_id: "All grow rooms"
        if room_id is None
        else next(f"{room['code']} · {room['name']}" for room in rooms if room["id"] == room_id),
        key="colonisation_room_filter",
    )

room_label = (
    "all grow rooms"
    if selected_room_id is None
    else next(f"{room['code']} · {room['name']}" for room in rooms if room["id"] == selected_room_id)
)
with scope_col:
    st.markdown(
        f'<div class="msra-flag" style="margin-top:26px;">'
        f'<span class="msra-flag-line" aria-hidden="true"></span>Scope: {ui._esc(room_label)}</div>',
        unsafe_allow_html=True,
    )

try:
    bags = services.list_bags(selected_room_id)
    mean_pct = services.room_mean_colonisation(selected_room_id)
except sqlite3.Error as exc:
    ui.query_error("substrate bags", exc)
    st.stop()

st.write("")

stat_col_a, stat_col_b, stat_col_c = st.columns(3, gap="medium")
with stat_col_a:
    with st.container(border=True, key="msra-card-a"):
        ui.render_stat(
            "Mean colonisation",
            "—" if mean_pct is None else f"{mean_pct:.1f}",
            unit="%",
            note="Mean of each bag's latest reading in scope",
        )
with stat_col_b:
    with st.container(border=True, key="msra-card-b"):
        colonising = int((bags["status"] == "Colonising").sum()) if not bags.empty else 0
        ui.render_stat(
            "Bags in scope",
            ui.fmt_int(len(bags)),
            unit="bags",
            note=f"{colonising} still colonising · {len(bags) - colonising} moved on",
        )
with stat_col_c:
    with st.container(border=True, key="msra-card-c"):
        readings_total = int(bags["reading_count"].sum()) if not bags.empty else 0
        ui.render_stat(
            "Readings recorded",
            ui.fmt_int(readings_total),
            unit="readings",
            note="Every percentage is stamped with its reading date",
        )

st.write("")
ui.section_head("Bag register", flag="Latest progress per bag", meta=f"{len(bags)} bags")

if bags.empty:
    ui.empty_state(
        "No bags registered in this room yet",
        "Use the register-bag form below to add the first block to this grow room. "
        "Bags appear here with their latest colonisation percentage.",
    )
else:
    status_tone = {
        "Colonising": "info",
        "Fruiting": "ok",
        "Contaminated": "danger",
        "Retired": "muted",
    }
    card_columns = st.columns(2, gap="medium")
    for position, row in enumerate(bags.itertuples(index=False)):
        latest = "—" if pd.isna(row.latest_pct) else f"{float(row.latest_pct):.0f}"
        tone = status_tone.get(row.status, "muted")
        bar_tone = "danger" if row.status == "Contaminated" else "warn" if row.status == "Retired" else ""
        latest_note = (
            "No readings yet"
            if pd.isna(row.latest_pct)
            else f"{row.reading_count} reading(s) · latest {ui.human_date(row.latest_reading_date)}"
        )
        with card_columns[position % 2]:
            st.markdown(
                f"""
                <div class="msra-bag">
                  <div class="msra-bag-top">
                    <div>
                      <div class="msra-bag-code">{ui._esc(row.bag_code)}</div>
                      <div class="msra-bag-meta">{ui._esc(row.strain_name)} · {ui._esc(row.room_code)}
                        · spawned {ui.human_date(row.spawned_on)}</div>
                    </div>
                    {ui.chip(row.status, tone)}
                  </div>
                  <div class="msra-bag-figures">
                    <div class="msra-bag-pct">{latest}<small>%</small></div>
                    <div class="msra-bag-meta">{ui._esc(latest_note)}</div>
                  </div>
                  {ui.progress_bar(None if pd.isna(row.latest_pct) else float(row.latest_pct), bar_tone)}
                  <div class="msra-bag-meta" style="margin-top:8px;">{ui._esc(ui.or_dash(row.substrate_recipe, ""))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

st.write("")
trend_col, reading_col = st.columns([1.4, 1], gap="medium")

with trend_col:
    with st.container(border=True, key="msra-card-anchor"):
        ui.section_head("Colonisation trend", flag="Selected bag", meta="Percentage per reading date")
        if bags.empty:
            ui.empty_state(
                "No bags in scope",
                "Register a bag or clear the grow-room filter to see a trend line.",
            )
        else:
            bag_ids = list(bags["id"])
            selected_bag_id = st.selectbox(
                "Bag",
                options=bag_ids,
                format_func=lambda bag_id: next(
                    f"{row.bag_code} · {row.strain_name} ({row.room_code})"
                    for row in bags.itertuples(index=False)
                    if row.id == bag_id
                ),
                key="colonisation_trend_bag",
            )
            readings = services.bag_readings(int(selected_bag_id))
            if readings.empty:
                ui.empty_state(
                    "No readings yet - add the first reading",
                    "This bag has no colonisation readings. Use the record-a-reading form beside "
                    "this chart: the trend line draws itself from the first entry.",
                )
            else:
                trend_frame = readings.assign(
                    reading_date=pd.to_datetime(readings["reading_date"])
                )
                chart = (
                    alt.Chart(trend_frame)
                    .mark_line(
                        point=alt.OverlayMarkDef(size=60, filled=True),
                        strokeWidth=2.4,
                        color=ui.CHART_COLORS[0],
                    )
                    .encode(
                        x=alt.X("reading_date:T", title="Reading date"),
                        y=alt.Y(
                            "colonisation_pct:Q",
                            title="Colonisation (%)",
                            scale=alt.Scale(domain=[0, 100]),
                        ),
                        tooltip=[
                            alt.Tooltip("reading_date:T", title="Date", format="%d %b %Y"),
                            alt.Tooltip("colonisation_pct:Q", title="Colonisation %"),
                            alt.Tooltip("notes:N", title="Notes"),
                        ],
                    )
                )
                ui.show_chart(chart, height=300, key="chart_bag_trend")
                st.caption(
                    f"{len(readings)} readings · first {ui.human_date(readings['reading_date'].iloc[0])} "
                    f"({ui.relative_days(readings['reading_date'].iloc[0])})"
                )

with reading_col:
    with st.container(border=True, key="msra-card-d"):
        ui.section_head("Record a reading", flag="Append to a bag")
        if bags.empty:
            ui.empty_state(
                "Register a bag first",
                "Readings attach to a bag, so add a bag with the form below before recording percentages.",
            )
        else:
            with st.form("add_reading_form", clear_on_submit=False):
                reading_bag_id = st.selectbox(
                    "Bag",
                    options=list(bags["id"]),
                    format_func=lambda bag_id: next(
                        row.bag_code for row in bags.itertuples(index=False) if row.id == bag_id
                    ),
                    key="reading_bag",
                )
                reading_date = st.date_input("Reading date", key="reading_date")
                colonisation_pct = st.number_input(
                    "Colonisation (%)",
                    min_value=0,
                    max_value=100,
                    value=60,
                    step=1,
                    key="reading_pct",
                    help="Whole percentage between 0 and 100.",
                )
                reading_notes = st.text_area(
                    "Notes",
                    key="reading_notes",
                    placeholder="Mycelium even, no sour smell.",
                    height=80,
                )
                submitted = st.form_submit_button("Save reading", type="primary", width="stretch")

            if submitted:
                try:
                    services.add_reading(
                        bag_id=int(reading_bag_id),
                        reading_date=reading_date,
                        colonisation_pct=colonisation_pct,
                        notes=reading_notes,
                    )
                except services.ValidationError as error:
                    st.error(str(error))
                except sqlite3.Error as error:
                    ui.query_error("the colonisation reading", error)
                else:
                    ui.flash(
                        "success",
                        f"Reading of {int(colonisation_pct)}% saved for {ui.human_date(reading_date)}.",
                    )
                    st.rerun()

with st.container(border=True, key="msra-card-e"):
    ui.section_head("Register a bag", flag="New substrate block", meta="Status defaults to Colonising")
    with st.form("register_bag_form", clear_on_submit=False):
        row_one = st.columns([1, 1, 1], gap="medium")
        bag_code = row_one[0].text_input("Bag code", key="new_bag_code", placeholder="BAG-2055")
        grow_room_id = row_one[1].selectbox(
            "Grow room",
            options=[room["id"] for room in rooms],
            format_func=lambda room_id: next(
                f"{room['code']} · {room['name']}" for room in rooms if room["id"] == room_id
            ),
            key="new_bag_room",
        )
        strain_id = row_one[2].selectbox(
            "Strain",
            options=[strain["id"] for strain in strains],
            format_func=lambda strain: next(
                entry["name"] for entry in strains if entry["id"] == strain
            ),
            key="new_bag_strain",
        )
        row_two = st.columns([1.3, 1, 1], gap="medium")
        substrate_recipe = row_two[0].selectbox(
            "Substrate recipe", options=list(SUBSTRATE_RECIPES), key="new_bag_recipe"
        )
        spawned_on = row_two[1].date_input("Spawned on", key="new_bag_spawned_on")
        status = row_two[2].selectbox(
            "Status",
            options=list(BAG_STATUSES),
            index=list(BAG_STATUSES).index(DEFAULT_BAG_STATUS),
            key="new_bag_status",
        )
        register = st.form_submit_button("Register bag", type="primary", width="stretch")

    if register:
        try:
            new_id = services.create_bag(
                bag_code=bag_code,
                grow_room_id=grow_room_id,
                strain_id=strain_id,
                substrate_recipe=substrate_recipe,
                spawned_on=spawned_on,
                status=status,
            )
        except services.ValidationError as error:
            st.error(str(error))
        except sqlite3.Error as error:
            ui.query_error("the new bag", error)
        else:
            ui.flash(
                "success",
                f"Bag {bag_code.strip()} registered in "
                f"{next(room['name'] for room in rooms if room['id'] == grow_room_id)} "
                f"with status {status} (id {new_id}).",
            )
            st.rerun()
