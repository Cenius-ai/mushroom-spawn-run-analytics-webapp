"""Contamination incident log: filters, table, by-type summary, resolution."""

from __future__ import annotations

import sqlite3

import altair as alt
import streamlit as st

from core import services, ui
from core.config import CONTAMINANT_TYPES, INCIDENT_SEVERITIES

ui.signed_in_page(
    "Contamination Log", ":material/warning:", context_label="Contamination incidents"
)

ui.page_head(
    "Contamination Log",
    "Contamination incidents",
    "Every flagged block, its severity and how it was resolved. Filter by room, status or "
    "contaminant, then mark an open incident resolved once the room is clear.",
)

try:
    rooms = services.list_grow_rooms()
    stats = services.incident_stats()
except sqlite3.Error as exc:
    ui.query_error("incident statistics", exc)
    st.stop()

if not rooms:
    ui.empty_state(
        "No grow rooms configured",
        "Reset the demo data from the sidebar to restore the seeded grow rooms.",
    )
    st.stop()

filter_a, filter_b, filter_c = st.columns(3, gap="medium")
with filter_a:
    room_filter = st.selectbox(
        "Grow room",
        options=[None] + [room["id"] for room in rooms],
        format_func=lambda room_id: "All grow rooms"
        if room_id is None
        else next(f"{room['code']} · {room['name']}" for room in rooms if room["id"] == room_id),
        key="incident_room_filter",
    )
with filter_b:
    status_filter = st.selectbox(
        "Status", options=[None, "Open", "Resolved"], format_func=lambda value: value or "All statuses",
        key="incident_status_filter",
    )
with filter_c:
    type_filter = st.selectbox(
        "Contaminant",
        options=[None] + list(CONTAMINANT_TYPES),
        format_func=lambda value: value or "All contaminants",
        key="incident_type_filter",
    )

filters_active = any([room_filter, status_filter, type_filter])

try:
    incidents = services.list_incidents(room_filter, status_filter, type_filter)
    type_counts = services.incident_type_counts()
except sqlite3.Error as exc:
    ui.query_error("contamination incidents", exc)
    st.stop()

st.write("")

stat_a, stat_b, stat_c, stat_d = st.columns(4, gap="medium")
with stat_a:
    with st.container(border=True, key="msra-card-a"):
        ui.render_stat("Open incidents", ui.fmt_int(stats["open"]), unit="open",
                       note="Awaiting an action and a resolved date")
with stat_b:
    with st.container(border=True, key="msra-card-b"):
        ui.render_stat("Resolved", ui.fmt_int(stats["resolved"]), unit="closed",
                       note="Resolved date stamped automatically")
with stat_c:
    with st.container(border=True, key="msra-card-c"):
        ui.render_stat("High severity open", ui.fmt_int(stats["open_high"]), unit="incidents",
                       note="Rectify before the next flush cycle")
with stat_d:
    with st.container(border=True, key="msra-card-d"):
        ui.render_stat("Logged all time", ui.fmt_int(stats["total"]), unit="incidents",
                       note=f"{len(type_counts)} contaminant types on record")

st.write("")
table_col, summary_col = st.columns([1.6, 1], gap="medium")

severity_tone = {"Low": "muted", "Medium": "warn", "High": "danger"}
status_tone = {"Open": "danger", "Resolved": "ok"}

with table_col:
    with st.container(border=True, key="msra-card-anchor"):
        ui.section_head(
            "Incident log",
            flag="Filtered view",
            meta=f"{len(incidents)} matching incidents",
        )
        if incidents.empty:
            if filters_active:
                ui.empty_state(
                    "No incidents match these filters",
                    "Clear the room, status or contaminant filter above to see the rest of the log, "
                    "or log the first incident with the form below.",
                )
            else:
                ui.empty_state(
                    "No incidents logged yet",
                    "Nothing has been flagged in this workspace. Log the first incident with the "
                    "form beside this table.",
                )
        else:
            table_rows = [
                [
                    ui.human_date(row.incident_date),
                    row.room,
                    ui.or_dash(row.bag_code, "Room-wide"),
                    row.contaminant_type,
                    row.severity,
                    row.status,
                    ui.human_date(row.resolved_on) if not ui.is_missing(row.resolved_on) else "—",
                ]
                for row in incidents.itertuples(index=False)
            ]
            ui.render_table(
                ["Date", "Room", "Bag", "Contaminant", "Severity", "Status", "Resolved"],
                table_rows,
            )

with summary_col:
    with st.container(border=True, key="msra-card-e"):
        ui.section_head("By contaminant type", flag="All time", meta=f"{stats['total']} incidents")
        if type_counts.empty:
            ui.empty_state(
                "Nothing to summarise",
                "Contaminant counts appear once at least one incident is logged.",
            )
        else:
            chart = (
                alt.Chart(type_counts)
                .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4, color=ui.CHART_COLORS[2])
                .encode(
                    y=alt.Y("contaminant_type:N", title=None, sort="-x"),
                    x=alt.X("incidents:Q", title="Incidents", axis=alt.Axis(tickMinStep=1)),
                    tooltip=[
                        alt.Tooltip("contaminant_type:N", title="Contaminant"),
                        alt.Tooltip("incidents:Q", title="Incidents"),
                        alt.Tooltip("open_incidents:Q", title="Still open"),
                        alt.Tooltip("high_severity:Q", title="High severity"),
                    ],
                )
            )
            ui.show_chart(chart, height=250, key="chart_type_counts")

st.write("")
queue_col, form_col = st.columns([1.6, 1], gap="medium")

with queue_col:
    with st.container(border=True, key="msra-card-f"):
        ui.section_head(
            "Open incident queue",
            flag="Mark resolved",
            meta="Resolution stamps today's date",
        )
        try:
            open_incidents = services.list_incidents(status="Open")
        except sqlite3.Error as exc:
            open_incidents = None
            ui.query_error("the open incident queue", exc)

        if open_incidents is not None and open_incidents.empty:
            ui.empty_state(
                "Nothing open right now",
                "Every logged incident has been resolved. New incidents appear here until they are "
                "marked resolved.",
            )
        elif open_incidents is not None:
            for row in open_incidents.itertuples(index=False):
                detail_col, action_col = st.columns([3, 1], gap="small", vertical_alignment="center")
                detail_col.markdown(
                    f"""
                    <div style="padding:6px 0;">
                      <div style="font-size:13.5px;font-weight:600;display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                        {ui._esc(row.contaminant_type)} · {ui._esc(row.room)}
                        {ui.chip(row.severity, severity_tone.get(row.severity, "muted"))}
                        {ui.chip(row.status, status_tone.get(row.status, "muted"))}
                      </div>
                      <div class="msra-bag-meta">
                        {ui._esc(ui.human_date(row.incident_date))} ({ui._esc(ui.relative_days(row.incident_date))})
                        · bag {ui._esc(ui.or_dash(row.bag_code, "room-wide"))} · {ui._esc(ui.or_dash(row.action_taken, "no action recorded yet"))}
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                with action_col:
                    if st.button("Mark resolved", key=f"resolve_{row.id}", width="stretch"):
                        try:
                            resolved = services.resolve_incident(int(row.id))
                        except sqlite3.Error as exc:
                            ui.query_error("the incident update", exc)
                        else:
                            if resolved:
                                ui.flash(
                                    "success",
                                    f"{row.contaminant_type} incident in {row.room} marked resolved.",
                                )
                                st.rerun()
                            else:
                                st.warning("That incident was already resolved.")

with form_col:
    with st.container(border=True, key="msra-card-form"):
        ui.section_head("Log an incident", flag="New entry")
        form_room_id = st.selectbox(
            "Grow room",
            options=[room["id"] for room in rooms],
            format_func=lambda room_id: next(
                f"{room['code']} · {room['name']}" for room in rooms if room["id"] == room_id
            ),
            key="log_incident_room",
        )
        try:
            room_bags = services.list_bags(int(form_room_id))
        except sqlite3.Error as exc:
            room_bags = None
            ui.query_error("the bags for this room", exc)

        bag_options: list[int | None] = [None]
        bag_labels = {None: "Room-wide (no specific bag)"}
        if room_bags is not None and not room_bags.empty:
            for row in room_bags.itertuples(index=False):
                bag_options.append(int(row.id))
                bag_labels[int(row.id)] = f"{row.bag_code} · {row.strain_name}"

        with st.form("log_incident_form", clear_on_submit=False):
            incident_bag_id = st.selectbox(
                "Bag",
                options=bag_options,
                format_func=lambda bag_id: bag_labels.get(bag_id, "Room-wide (no specific bag)"),
                key="log_incident_bag",
            )
            incident_date = st.date_input("Incident date", key="log_incident_date")
            contaminant_type = st.selectbox(
                "Contaminant type", options=list(CONTAMINANT_TYPES), key="log_incident_type"
            )
            severity = st.selectbox(
                "Severity",
                options=list(INCIDENT_SEVERITIES),
                index=1,
                key="log_incident_severity",
            )
            action_taken = st.text_area(
                "Action taken",
                key="log_incident_action",
                placeholder="Isolated the bag, fogged the room, swapped filters.",
                height=80,
            )
            submitted = st.form_submit_button("Log incident", type="primary", width="stretch")

        if submitted:
            try:
                services.log_incident(
                    grow_room_id=int(form_room_id),
                    incident_date=incident_date,
                    contaminant_type=contaminant_type,
                    severity=severity,
                    action_taken=action_taken,
                    bag_id=None if incident_bag_id is None else int(incident_bag_id),
                )
            except services.ValidationError as error:
                st.error(str(error))
            except sqlite3.Error as error:
                ui.query_error("the incident", error)
            else:
                ui.flash(
                    "success",
                    f"{contaminant_type} incident logged at {severity} severity with status Open.",
                )
                st.rerun()
