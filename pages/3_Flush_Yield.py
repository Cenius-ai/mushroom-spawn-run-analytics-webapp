"""Flush yield: strain bar chart, per-flush line chart, recent harvest table."""

from __future__ import annotations

import sqlite3

import altair as alt
import streamlit as st
from pandas import isna

from core import services, ui
from core.config import DEFAULT_WINDOW_DAYS, WINDOW_OPTIONS

ui.signed_in_page("Flush Yield", ":material/scale:", context_label="Harvest yield")

ui.page_head(
    "Flush Yield",
    "Flush yield by strain",
    "Wet and dry weights for every harvest, compared across strains and followed flush by "
    "flush. The strain and window filters scope the charts and the harvest table together.",
)

try:
    strains = services.list_strains()
    bags = services.list_bags()
except sqlite3.Error as exc:
    ui.query_error("strains and bags", exc)
    st.stop()

if not strains or bags.empty:
    ui.empty_state(
        "No strains or bags configured",
        "Reset the demo data from the sidebar to restore the seeded strains and substrate bags.",
    )
    st.stop()

filter_strain_col, filter_window_col, _spacer = st.columns([0.5, 0.5, 1], gap="medium")
with filter_strain_col:
    strain_options = [None] + [strain["id"] for strain in strains]
    selected_strain_id = st.selectbox(
        "Strain",
        options=strain_options,
        format_func=lambda strain_id: "All strains"
        if strain_id is None
        else next(entry["name"] for entry in strains if entry["id"] == strain_id),
        key="yield_strain_filter",
    )
with filter_window_col:
    selected_window = st.segmented_control(
        "Window",
        options=list(WINDOW_OPTIONS),
        default=DEFAULT_WINDOW_DAYS,
        format_func=lambda days: f"Last {days} days",
        key="yield_window",
    )
window_days = selected_window or DEFAULT_WINDOW_DAYS

try:
    flushes = services.list_flush_yields(selected_strain_id, window_days)
    by_strain = services.yield_by_strain(window_days)
except (sqlite3.Error, services.ValidationError) as exc:
    ui.query_error("flush yields", exc)
    st.stop()

# The line chart follows the selected strain; with "All strains" it follows the
# strain with the largest wet yield in the window so the chart is never empty.
line_strain_id = selected_strain_id
if line_strain_id is None and not by_strain.empty:
    top_strain = by_strain.iloc[0]["strain"]
    line_strain_id = next((s["id"] for s in strains if s["name"] == top_strain), strains[0]["id"])
if line_strain_id is None:
    line_strain_id = strains[0]["id"]
line_strain_name = next(entry["name"] for entry in strains if entry["id"] == line_strain_id)

st.write("")

total_wet = float(flushes["wet_weight_g"].sum()) if not flushes.empty else 0.0
total_dry = float(flushes["dry_weight_g"].sum()) if not flushes.empty else 0.0
ratio = (total_dry / total_wet) if total_wet else None

stat_a, stat_b, stat_c, stat_d = st.columns(4, gap="medium")
with stat_a:
    with st.container(border=True, key="msra-card-a"):
        ui.render_stat(
            f"Wet yield · last {window_days} days",
            ui.fmt_g(total_wet, unit=False),
            unit="kg" if total_wet >= 1000 else "g",
            note=f"{len(flushes)} harvests in scope",
        )
with stat_b:
    with st.container(border=True, key="msra-card-b"):
        ui.render_stat(
            "Dry yield",
            ui.fmt_g(total_dry, unit=False),
            unit="kg" if total_dry >= 1000 else "g",
            note="Sum of recorded dry weights",
        )
with stat_c:
    with st.container(border=True, key="msra-card-c"):
        ui.render_stat(
            "Dry / wet ratio",
            "—" if ratio is None else f"{ratio * 100:.1f}",
            unit="%",
            note="Dry weight as a share of wet weight",
        )
with stat_d:
    with st.container(border=True, key="msra-card-d"):
        ui.render_stat(
            "Strains harvested",
            ui.fmt_int(by_strain.shape[0]),
            unit="strains",
            note=f"Line chart follows {line_strain_name}",
        )

st.write("")
chart_left, chart_right = st.columns([1.35, 1], gap="medium")

with chart_left:
    with st.container(border=True, key="msra-card-anchor"):
        ui.section_head(
            "Total wet yield by strain",
            flag=f"Last {window_days} days",
            meta="Sorted descending",
        )
        if by_strain.empty:
            ui.empty_state(
                "No flushes recorded in this window",
                f"Nothing was harvested in the last {window_days} days. Widen the window to 90 days "
                "or record a flush with the form below.",
            )
        else:
            strain_frame = by_strain.assign(wet_kg=by_strain["wet_g"] / 1000.0)
            bars = (
                alt.Chart(strain_frame)
                .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, color=ui.CHART_COLORS[0])
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
            labels = (
                alt.Chart(strain_frame)
                .mark_text(dy=-8, fontSize=11, color="#5f665a")
                .encode(
                    x=alt.X("strain:N", sort="-y"),
                    y="wet_kg:Q",
                    text=alt.Text("wet_kg:Q", format=".2f"),
                )
            )
            ui.show_chart(bars + labels, height=300, key="chart_yield_by_strain")

with chart_right:
    with st.container(border=True, key="msra-card-e"):
        ui.section_head(
            "Wet weight by flush number",
            flag=line_strain_name,
            meta="Mean across bags, band shows min-max",
        )
        profile = services.flush_profile_by_number(line_strain_id, window_days)
        if profile.empty:
            ui.empty_state(
                "No flushes for this strain in the window",
                f"{line_strain_name} has no harvests in the last {window_days} days. "
                "Pick another strain or widen the window.",
            )
        else:
            band = (
                alt.Chart(profile)
                .mark_area(opacity=0.14, color=ui.CHART_COLORS[0])
                .encode(
                    x=alt.X("flush_number:O", title="Flush number"),
                    y=alt.Y("min_wet_g:Q", title="Wet weight (g)", scale=alt.Scale(zero=False)),
                    y2="max_wet_g:Q",
                )
            )
            line = (
                alt.Chart(profile)
                .mark_line(point=alt.OverlayMarkDef(size=60, filled=True), strokeWidth=2.4,
                           color=ui.CHART_COLORS[0])
                .encode(
                    x=alt.X("flush_number:O", title="Flush number"),
                    y=alt.Y("mean_wet_g:Q", title="Wet weight (g)", scale=alt.Scale(zero=False)),
                    tooltip=[
                        alt.Tooltip("flush_number:O", title="Flush"),
                        alt.Tooltip("mean_wet_g:Q", title="Mean wet (g)", format=".0f"),
                        alt.Tooltip("min_wet_g:Q", title="Min (g)", format=".0f"),
                        alt.Tooltip("max_wet_g:Q", title="Max (g)", format=".0f"),
                        alt.Tooltip("flushes:Q", title="Harvests"),
                    ],
                )
            )
            ui.show_chart(band + line, height=300, key="chart_flush_profile")

st.write("")
table_col, form_col = st.columns([1.55, 1], gap="medium")

with table_col:
    with st.container(border=True, key="msra-card-f"):
        ui.section_head(
            "Recent flushes",
            flag="Harvest log",
            meta=f"{len(flushes)} rows · dry/wet ratio per row",
        )
        if flushes.empty:
            ui.empty_state(
                "No flushes match these filters",
                "Clear the strain filter or widen the window - or record the first flush with the "
                "form beside this table.",
            )
        else:
            recent = flushes.head(15)
            table_rows = []
            for row in recent.itertuples(index=False):
                dry_value = "—" if isna(row.dry_weight_g) else f"{row.dry_weight_g:,.1f}"
                ratio_value = "—" if isna(row.dry_wet_ratio) else f"{row.dry_wet_ratio * 100:.1f}%"
                table_rows.append(
                    [
                        ui.human_date(row.harvested_on),
                        row.bag_code,
                        row.strain,
                        row.room,
                        int(row.flush_number),
                        f"{row.wet_weight_g:,.1f}",
                        dry_value,
                        ratio_value,
                    ]
                )
            ui.render_table(
                ["Harvest", "Bag", "Strain", "Room", "Flush", "Wet (g)", "Dry (g)", "Dry/wet"],
                table_rows,
                numeric_columns=[4, 5, 6, 7],
            )
            if len(flushes) > len(recent):
                st.caption(
                    f"Showing the {len(recent)} most recent of {len(flushes)} harvests in this window."
                )

with form_col:
    with st.container(border=True, key="msra-card-form"):
        ui.section_head("Record a flush", flag="New harvest")
        bag_labels = {
            row.id: f"{row.bag_code} · {row.strain_name}"
            for row in bags.itertuples(index=False)
        }
        with st.form("record_flush_form", clear_on_submit=False):
            flush_bag_id = st.selectbox(
                "Bag",
                options=list(bag_labels),
                format_func=lambda bag_id: bag_labels[bag_id],
                key="flush_bag",
            )
            flush_number = st.number_input(
                "Flush number",
                min_value=1,
                max_value=20,
                value=int(services.next_flush_number(int(flush_bag_id))),
                step=1,
                key="flush_number",
            )
            harvested_on = st.date_input("Harvest date", key="flush_harvested_on")
            weight_col_a, weight_col_b = st.columns(2, gap="small")
            wet_weight = weight_col_a.number_input(
                "Wet weight (g)",
                min_value=0.0,
                max_value=20000.0,
                value=420.0,
                step=10.0,
                key="flush_wet",
            )
            dry_weight = weight_col_b.number_input(
                "Dry weight (g)",
                min_value=0.0,
                max_value=20000.0,
                value=46.0,
                step=1.0,
                key="flush_dry",
            )
            flush_notes = st.text_area(
                "Notes", key="flush_notes", placeholder="First flush, dense cluster.", height=70
            )
            submitted = st.form_submit_button("Save flush", type="primary", width="stretch")

        if submitted:
            try:
                services.record_flush(
                    bag_id=int(flush_bag_id),
                    flush_number=flush_number,
                    harvested_on=harvested_on,
                    wet_weight_g=wet_weight,
                    dry_weight_g=dry_weight,
                    notes=flush_notes,
                )
            except services.ValidationError as error:
                st.error(str(error))
            except sqlite3.Error as error:
                ui.query_error("the flush", error)
            else:
                ui.flash(
                    "success",
                    f"Flush {int(flush_number)} saved: {wet_weight:.0f} g wet / {dry_weight:.0f} g dry.",
                )
                st.rerun()
