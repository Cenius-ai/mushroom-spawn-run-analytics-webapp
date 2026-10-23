"""Humidity and CO2 threshold table with validated inline editing."""

from __future__ import annotations

import sqlite3

import streamlit as st

from core import services, ui
from core.config import THRESHOLD_METRIC_LABELS

ui.signed_in_page("Thresholds", ":material/tune:", context_label="Room environment thresholds")

ui.page_head(
    "Thresholds",
    "Humidity and CO2 thresholds",
    "One humidity row and one CO2 row per grow room: the range each room is held inside. "
    "Edit a row in place - the range must keep min below max and every save stamps an update time.",
)

filter_col, note_col = st.columns([0.55, 1.45], gap="medium")
with filter_col:
    metric_choice = st.segmented_control(
        "Metric",
        options=["all", "humidity_pct", "co2_ppm"],
        default="all",
        format_func=lambda value: "All metrics" if value == "all" else THRESHOLD_METRIC_LABELS[value],
        key="threshold_metric_filter",
    )
metric_filter = None if (metric_choice or "all") == "all" else metric_choice
with note_col:
    st.markdown(
        '<div class="msra-flag" style="margin-top:26px;">'
        '<span class="msra-flag-line" aria-hidden="true"></span>'
        "Thresholds are seeded per grow room and stored in the workspace database"
        "</div>",
        unsafe_allow_html=True,
    )

try:
    thresholds = services.list_thresholds(metric_filter)
except sqlite3.Error as exc:
    ui.query_error("the threshold table", exc)
    st.stop()

st.write("")

humidity_rows = int((thresholds["metric"] == "humidity_pct").sum()) if not thresholds.empty else 0
co2_rows = int((thresholds["metric"] == "co2_ppm").sum()) if not thresholds.empty else 0
last_updated = thresholds["updated_at"].max() if not thresholds.empty else None

stat_a, stat_b, stat_c = st.columns(3, gap="medium")
with stat_a:
    with st.container(border=True, key="msra-card-a"):
        ui.render_stat(
            "Configured rows",
            ui.fmt_int(len(thresholds)),
            unit="rows",
            note=f"{humidity_rows} humidity · {co2_rows} CO2 in this view",
        )
with stat_b:
    with st.container(border=True, key="msra-card-b"):
        ui.render_stat(
            "Metrics tracked",
            ui.fmt_int(thresholds["metric"].nunique() if not thresholds.empty else 0),
            unit="metrics",
            note="Humidity in % and CO2 in ppm",
        )
with stat_c:
    with st.container(border=True, key="msra-card-c"):
        ui.render_stat(
            "Last updated",
            ui.human_date(last_updated),
            note=ui.relative_days(last_updated) if last_updated else "No rows yet",
        )

st.write("")
table_col, edit_col = st.columns([1.5, 1], gap="medium")

with table_col:
    with st.container(border=True, key="msra-card-anchor"):
        ui.section_head(
            "Threshold table",
            flag="One row per room and metric",
            meta=f"{len(thresholds)} rows",
        )
        if thresholds.empty:
            ui.empty_state(
                "No thresholds configured",
                "Reset the demo data from the sidebar to restore the seeded humidity and CO2 ranges "
                "- four grow rooms, two metrics each.",
            )
        else:
            rows = []
            for row in thresholds.itertuples(index=False):
                rows.append(
                    "<tr>"
                    f"<td>{ui._esc(row.room_code)}</td>"
                    f"<td>{ui._esc(row.room)}</td>"
                    f"<td>{ui._esc(THRESHOLD_METRIC_LABELS.get(row.metric, row.metric))}</td>"
                    f'<td class="is-num">{ui._esc(f"{row.min_value:g}")}</td>'
                    f'<td class="is-num">{ui._esc(f"{row.max_value:g}")}</td>'
                    f"<td>{ui._esc(row.unit)}</td>"
                    f"<td>{ui._esc(ui.human_date(row.updated_at))}</td>"
                    "</tr>"
                )
            st.markdown(
                '<div class="msra-table-wrap"><table class="msra-table">'
                "<thead><tr>"
                "<th>Room</th><th>Name</th><th>Metric</th>"
                '<th class="is-num">Min</th><th class="is-num">Max</th>'
                "<th>Unit</th><th>Updated</th>"
                "</tr></thead><tbody>"
                + "".join(rows)
                + "</tbody></table></div>",
                unsafe_allow_html=True,
            )

with edit_col:
    with st.container(border=True, key="msra-card-d"):
        ui.section_head("Edit a range", flag="Min must stay below max")
        if thresholds.empty:
            ui.empty_state(
                "Nothing to edit",
                "Restore the seeded ranges with the demo data reset in the sidebar first.",
            )
        else:
            row_labels = {
                int(row.id): f"{row.room_code} · {THRESHOLD_METRIC_LABELS.get(row.metric, row.metric)}"
                for row in thresholds.itertuples(index=False)
            }
            selected_row_id = st.selectbox(
                "Threshold row",
                options=list(row_labels),
                format_func=lambda row_id: row_labels[row_id],
                key="threshold_edit_row",
            )
            current = thresholds[thresholds["id"] == selected_row_id].iloc[0]
            with st.form("edit_threshold_form", clear_on_submit=False):
                value_col_a, value_col_b = st.columns(2, gap="small")
                new_min = value_col_a.number_input(
                    f"Minimum ({current['unit']})",
                    value=float(current["min_value"]),
                    step=1.0,
                    key=f"threshold_min_{selected_row_id}",
                )
                new_max = value_col_b.number_input(
                    f"Maximum ({current['unit']})",
                    value=float(current["max_value"]),
                    step=1.0,
                    key=f"threshold_max_{selected_row_id}",
                )
                st.caption(
                    f"Currently {current['min_value']:g}\u2013{current['max_value']:g} {current['unit']} "
                    f"for {current['room']}."
                )
                saved = st.form_submit_button("Save threshold", type="primary", width="stretch")

            if saved:
                try:
                    updated = services.update_threshold(
                        int(selected_row_id), min_value=new_min, max_value=new_max
                    )
                except services.ValidationError as error:
                    st.error(str(error))
                except sqlite3.Error as error:
                    ui.query_error("the threshold update", error)
                else:
                    ui.flash(
                        "success",
                        f"Saved {updated['min_value']:g}\u2013{updated['max_value']:g} "
                        f"{updated['unit']} for {updated['room']} · updated {ui.human_date(updated['updated_at'])}.",
                    )
                    st.rerun()
