"""Dashboard: the run overview.

Four KPIs, colonisation by grow room, yield by strain, incidents by type and a
per-room humidity / CO2 threshold strip - all read through core.services.
"""

from __future__ import annotations

import sqlite3

import altair as alt
import streamlit as st

from core import services, ui
from core.config import DEFAULT_WINDOW_DAYS, WINDOW_OPTIONS

ui.signed_in_page(
    "Dashboard",
    ":material/insights:",
    context_label="Run overview",
    meta=("Live demo dataset", "SQLite · local"),
)

ui.page_head(
    "Dashboard",
    "Run overview",
    "Colonisation, flush yield and contamination across every grow room, read live from the "
    "workspace database. Switch the window to re-scope yields and incidents.",
)

filter_col, hint_col = st.columns([0.55, 1.45], gap="medium")
with filter_col:
    selected_window = st.segmented_control(
        "Window",
        options=list(WINDOW_OPTIONS),
        default=DEFAULT_WINDOW_DAYS,
        format_func=lambda days: f"Last {days} days",
        key="dashboard_window",
    )
window_days = selected_window or DEFAULT_WINDOW_DAYS
with hint_col:
    st.markdown(
        f'<div class="msra-flag" style="margin-top:26px;">'
        f'<span class="msra-flag-line" aria-hidden="true"></span>'
        f"Yields and incidents scoped to the last {window_days} days"
        "</div>",
        unsafe_allow_html=True,
    )

try:
    kpis = services.overview_kpis(window_days)
    by_room = services.colonisation_by_room()
    by_strain = services.yield_by_strain(window_days)
    by_type = services.incidents_by_type(window_days)
    thresholds = services.threshold_summary()
    incident_stats = services.incident_stats()
    rooms = services.list_grow_rooms()
except (sqlite3.Error, services.ValidationError) as exc:
    ui.query_error("the dashboard", exc)
    st.stop()

st.write("")

# ---------------------------------------------------------------- row 1
anchor_col, stat_a_col, stat_b_col = st.columns([1.5, 1, 1], gap="medium")

with anchor_col:
    with st.container(border=True, key="msra-card-anchor"):
        ui.section_head(
            "Colonisation by grow room",
            flag="Latest reading per bag",
            meta=f"{len(by_room)} rooms with readings",
        )
        if by_room.empty:
            ui.empty_state(
                "No colonisation readings yet",
                "Add the first reading on the Colonisation page - the room means appear here "
                "as soon as one bag has a reading.",
            )
        else:
            bars = (
                alt.Chart(by_room)
                .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, color=ui.CHART_COLORS[0])
                .encode(
                    x=alt.X("room_code:N", title="Grow room", axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("mean_pct:Q", title="Mean colonisation (%)", scale=alt.Scale(domain=[0, 100])),
                    tooltip=[
                        alt.Tooltip("room:N", title="Room"),
                        alt.Tooltip("mean_pct:Q", title="Mean colonisation", format=".1f"),
                        alt.Tooltip("bags_with_readings:Q", title="Bags with readings"),
                    ],
                )
            )
            labels = (
                alt.Chart(by_room)
                .mark_text(dy=-8, fontSize=11, color="#5f665a")
                .encode(
                    x=alt.X("room_code:N", sort="-y"),
                    y="mean_pct:Q",
                    text=alt.Text("mean_pct:Q", format=".0f"),
                )
            )
            ui.show_chart(bars + labels, height=300, key="chart_room_colonisation")

with stat_a_col:
    with st.container(border=True, key="msra-card-a"):
        ui.render_stat(
            "Colonising bags",
            ui.fmt_int(kpis["colonising_bags"]),
            unit="bags",
            note=f"{kpis['total_bags']} bags registered across {len(rooms)} grow rooms",
        )

with stat_b_col:
    with st.container(border=True, key="msra-card-b"):
        ui.render_stat(
            "Mean latest colonisation",
            "—" if kpis["mean_latest_pct"] is None else f"{kpis['mean_latest_pct']:.1f}",
            unit="%",
            note=f"Across {kpis['bags_with_readings']} active bags (colonising + fruiting)",
        )

# ---------------------------------------------------------------- row 2
stat_c_col, stat_d_col, strain_col = st.columns([1, 1, 1.5], gap="medium")

with stat_c_col:
    with st.container(border=True, key="msra-card-c"):
        change = kpis["wet_yield_change_pct"]
        if change is None:
            delta_text, delta_tone = "", "flat"
        elif change > 0:
            delta_text, delta_tone = f"▲ {change:+.1f}% vs previous {window_days} days", "up"
        elif change < 0:
            delta_text, delta_tone = f"▼ {change:+.1f}% vs previous {window_days} days", "down"
        else:
            delta_text, delta_tone = f"Flat vs previous {window_days} days", "flat"
        ui.render_stat(
            f"Wet yield · last {window_days} days",
            ui.fmt_g(kpis["wet_yield_g"], unit=False),
            unit="kg" if kpis["wet_yield_g"] >= 1000 else "g",
            delta=delta_text,
            delta_tone=delta_tone,
            note=f"{kpis['flushes_in_window']} flushes harvested in the window",
        )

with stat_d_col:
    with st.container(border=True, key="msra-card-d"):
        ui.render_stat(
            "Open incidents",
            ui.fmt_int(kpis["open_incidents"]),
            unit="open",
            note=(
                f"{kpis['incidents_in_window']} logged in the last {window_days} days · "
                f"{incident_stats['open_high']} high severity open"
            ),
        )

with strain_col:
    with st.container(border=True, key="msra-card-e"):
        ui.section_head(
            "Wet yield by strain",
            flag=f"Last {window_days} days",
            meta="Sorted by total wet weight",
        )
        if by_strain.empty:
            ui.empty_state(
                "No flushes in this window",
                f"No harvests were recorded in the last {window_days} days. Widen the window to "
                "90 days or record a flush on the Flush Yield page.",
            )
        else:
            strain_frame = by_strain.assign(wet_kg=by_strain["wet_g"] / 1000.0)
            chart = (
                alt.Chart(strain_frame)
                .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, color=ui.CHART_COLORS[1])
                .encode(
                    x=alt.X("strain:N", title="Strain", sort="-y", axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("wet_kg:Q", title="Wet yield (kg)"),
                    tooltip=[
                        alt.Tooltip("strain:N", title="Strain"),
                        alt.Tooltip("wet_kg:Q", title="Wet (kg)", format=".2f"),
                        alt.Tooltip("dry_g:Q", title="Dry (g)", format=".0f"),
                        alt.Tooltip("flushes:Q", title="Flushes"),
                    ],
                )
            )
            ui.show_chart(chart, height=280, key="chart_yield_strain")

# ---------------------------------------------------------------- row 3
type_col, strip_col = st.columns([1, 1.7], gap="medium")

with type_col:
    with st.container(border=True, key="msra-card-f"):
        ui.section_head("Incidents by contaminant", flag=f"Last {window_days} days")
        if by_type.empty:
            ui.empty_state(
                "No incidents in this window",
                f"Nothing was logged in the last {window_days} days. Widen the window to 90 days "
                "or log an incident on the Contamination Log page.",
            )
        else:
            chart = (
                alt.Chart(by_type)
                .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4, color=ui.CHART_COLORS[2])
                .encode(
                    y=alt.Y("contaminant_type:N", title=None, sort="-x"),
                    x=alt.X("incidents:Q", title="Incidents", axis=alt.Axis(tickMinStep=1)),
                    tooltip=[
                        alt.Tooltip("contaminant_type:N", title="Contaminant"),
                        alt.Tooltip("incidents:Q", title="Incidents"),
                    ],
                )
            )
            ui.show_chart(chart, height=260, key="chart_incident_type")

with strip_col:
    with st.container(border=True, key="msra-card-strip"):
        ui.section_head(
            "Humidity and CO2 thresholds",
            flag="Per grow room",
            meta=f"{len(thresholds) * 2} rows seeded",
        )
        if thresholds.empty:
            ui.empty_state(
                "No thresholds configured",
                "Reset the demo data from the sidebar to restore the seeded humidity and CO2 ranges.",
            )
        else:
            cells = []
            for row in thresholds.itertuples(index=False):
                cells.append(
                    '<div class="msra-strip-cell">'
                    f'<div class="msra-strip-code">{ui._esc(row.room_code)}</div>'
                    f'<div class="msra-strip-room">{ui._esc(row.room)}</div>'
                    f'<div class="msra-strip-value"><span>Humidity</span><span>{ui._esc(ui.or_dash(row.humidity))}</span></div>'
                    f'<div class="msra-strip-value"><span>CO2</span><span>{ui._esc(ui.or_dash(row.co2))}</span></div>'
                    "</div>"
                )
            st.markdown(f'<div class="msra-strip">{"".join(cells)}</div>', unsafe_allow_html=True)
            st.markdown(
                '<p style="margin:12px 0 0 0;font-size:13px;">'
                '<a class="msra-link" href="/Thresholds" target="_self">Adjust threshold ranges</a>'
                " &middot; every save stamps the row's update time.</p>",
                unsafe_allow_html=True,
            )
