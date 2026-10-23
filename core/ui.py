"""Shared visual system: committed design tokens, page chrome, sidebar, charts.

The committed direction is a calm product surface: warm off-white canvas,
one green accent spent only where it carries meaning, dense data cells with
16-20px radii and 1px borders, and the signature "flag" callout - a hairline
leader into a 10px uppercase label - on every key metric.

All colour literals live in the single ``:root`` block below; components use
``var(--token)``. Chart libraries receive the hex twins, never ``oklch()``.
"""

from __future__ import annotations

import html
import logging
from datetime import date, datetime
from typing import Any, Iterable, Sequence

import altair as alt
import streamlit as st
from streamlit.errors import StreamlitPageNotFoundError

from core import auth, db
from core.config import APP_NAME, SIGN_IN_PAGE
from core.seed import reset_demo_data

# --------------------------------------------------------------------------
# Design tokens (single source of truth)
# --------------------------------------------------------------------------
TOKENS = {
    "card": "#fefffc",
    "ring": "#528a54",
    "muted": "#eaeee7",
    "accent": "#528a54",
    "border": "#dcdfd9",
    "primary": "#1a2213",
    "on-accent": "#111111",
    "secondary": "#eaeee7",
    "background": "#f8fcf5",
    "foreground": "#10150b",
    "on-primary": "#ffffff",
    "destructive": "#c9302d",
    "on-secondary": "#10150b",
    "on-destructive": "#ffffff",
    "card-foreground": "#10150b",
    "muted-foreground": "#5f665a",
}

# Accent text needs >=4.5:1 on the canvas, so links/meta accents use the
# darker green twin rather than the fill accent.
ACCENT_TEXT = "#3a6b3c"
WARN_TEXT = "#7a4b07"
WARN_BG = "#fbf1de"
DANGER_BG = "#fbe9e8"
OK_BG = "#e8f1e4"
INFO_BG = "#e9eef1"

# Categorical chart set: accent first, then CVD-safe hues measured >=3:1 on
# the card surface. Never oklch()/var() - Vega-Lite cannot parse those.
CHART_COLORS = ["#528a54", "#0072B2", "#D55E00", "#009E73", "#CC79A7"]

CSS = f"""
/* Self-hosted Lexend (variable, latin subset). Streamlit's static file server
   serves /app/static/... from the repo's static/ directory - no remote font. */
@font-face {{
  font-family: 'Lexend';
  font-style: normal;
  font-weight: 100 900;
  font-display: swap;
  src: url('/app/static/fonts/lexend-latin.woff2') format('woff2');
}}

:root {{
  --card: {TOKENS['card']};
  --ring: {TOKENS['ring']};
  --muted: {TOKENS['muted']};
  --accent: {TOKENS['accent']};
  --border: {TOKENS['border']};
  --primary: {TOKENS['primary']};
  --on-accent: {TOKENS['on-accent']};
  --secondary: {TOKENS['secondary']};
  --background: {TOKENS['background']};
  --foreground: {TOKENS['foreground']};
  --on-primary: {TOKENS['on-primary']};
  --destructive: {TOKENS['destructive']};
  --on-secondary: {TOKENS['on-secondary']};
  --on-destructive: {TOKENS['on-destructive']};
  --card-foreground: {TOKENS['card-foreground']};
  --muted-foreground: {TOKENS['muted-foreground']};
  --accent-text: {ACCENT_TEXT};
  --warn-text: {WARN_TEXT};
  --warn-bg: {WARN_BG};
  --danger-bg: {DANGER_BG};
  --ok-bg: {OK_BG};
  --info-bg: {INFO_BG};
  --font-body: 'Lexend', system-ui, -apple-system, 'Segoe UI', sans-serif;
  --radius-card: 18px;
  --radius-control: 10px;
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
}}

/* ---------- canvas + chrome ---------- */
html, body, [data-testid="stAppViewContainer"], .stApp {{
  font-family: var(--font-body);
  background: var(--background);
  color: var(--foreground);
}}
.stApp {{ font-size: 15px; }}
[data-testid="stHeader"] {{
  background: transparent;
  height: 2.4rem;
}}
[data-testid="stDecoration"] {{ display: none; }}
[data-testid="stMainBlockContainer"], .block-container {{
  padding-top: 0.9rem;
  padding-bottom: 3rem;
  max-width: 1460px;
}}
[data-testid="stSidebar"] {{
  background: var(--card);
  border-right: 1px solid var(--border);
}}
[data-testid="stSidebar"] .block-container {{ padding-top: 1rem; }}
[data-testid="stSidebarNav"] {{ padding-top: 0.25rem; }}
[data-testid="stSidebarNavLink"] {{
  border-radius: var(--radius-control);
  transition: background-color 80ms steps(1);
}}
[data-testid="stSidebarNavLink"] span {{ font-size: 14px; font-weight: 500; }}
[data-testid="stSidebarNavLink"]:hover {{ background: var(--secondary); }}
[data-testid="stSidebarNavLink"][aria-current="page"] {{
  background: var(--ok-bg);
  box-shadow: inset 3px 0 0 var(--accent);
}}
[data-testid="stSidebarNavLink"][aria-current="page"] span {{ font-weight: 600; color: var(--primary); }}

/* ---------- typography ---------- */
h1, h2, h3, h4, h5 {{ font-family: var(--font-body); color: var(--foreground); }}
p, li, span, label, div {{ font-family: var(--font-body); }}
.msra-head {{ margin: 0 0 var(--space-4) 0; }}
.msra-head h1 {{
  font-size: clamp(1.7rem, 1.2rem + 1.2vw, 2.1rem);
  line-height: 1.12;
  font-weight: 600;
  letter-spacing: -0.02em;
  margin: var(--space-2) 0 var(--space-1) 0;
}}
.msra-head p {{
  margin: 0;
  font-size: 0.875rem;
  line-height: 1.5;
  color: var(--muted-foreground);
  max-width: 74ch;
}}
.msra-flag {{
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--muted-foreground);
  line-height: 1.2;
}}
.msra-flag-line {{
  display: inline-block;
  width: 16px;
  height: 1px;
  background: var(--accent);
  flex: 0 0 auto;
}}
.msra-section-head {{
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-3);
  flex-wrap: wrap;
  margin-bottom: var(--space-3);
}}
.msra-section-title {{ font-size: 1rem; font-weight: 600; letter-spacing: -0.01em; margin: 6px 0 0 0; }}
.msra-section-meta {{ font-size: 12px; color: var(--muted-foreground); }}
.msra-link {{ color: var(--accent-text); font-weight: 600; text-decoration: none; border-bottom: 1px solid var(--ring); }}
.msra-link:hover {{ color: var(--primary); border-bottom-color: var(--primary); }}
.msra-link:focus-visible {{ outline: 2px solid var(--ring); outline-offset: 2px; }}

/* ---------- top bar ---------- */
.msra-topbar {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  flex-wrap: wrap;
  border: 1px solid var(--border);
  background: var(--card);
  border-radius: 14px;
  padding: 10px 16px;
  margin-bottom: var(--space-4);
}}
.msra-brand {{ display: flex; align-items: center; gap: 10px; min-width: 0; }}
.msra-brand-mark {{
  width: 28px; height: 28px; border-radius: 9px;
  background: var(--accent); color: var(--on-accent);
  display: grid; place-items: center;
  font-size: 13px; font-weight: 700; letter-spacing: -0.02em;
}}
.msra-brand-name {{ font-size: 13px; font-weight: 600; letter-spacing: 0.01em; }}
.msra-brand-sub {{ font-size: 11.5px; color: var(--muted-foreground); }}
.msra-topbar-meta {{
  display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
  font-size: 12px; color: var(--muted-foreground);
}}
.msra-meta-item {{ display: inline-flex; align-items: center; gap: 6px; }}
.msra-dot {{ width: 6px; height: 6px; border-radius: 50%; background: var(--accent); display: inline-block; }}

/* ---------- cards (keyed containers) ---------- */
[class*="st-key-msra-card"] {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 18px 20px;
}}
.st-key-msra-card-anchor {{ padding: 18px 20px; }}
.st-key-msra-card-accent {{
  background: var(--ok-bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 16px 18px;
}}
[data-testid="stForm"] {{
  background: transparent;
  border: none;
  padding: 0;
}}

/* ---------- stat cells ---------- */
.msra-stat-value {{
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 1.85rem;
  font-weight: 600;
  letter-spacing: -0.025em;
  line-height: 1.15;
  font-variant-numeric: tabular-nums;
  color: var(--foreground);
  margin-top: var(--space-2);
}}
.msra-stat-unit {{ font-size: 0.8rem; font-weight: 500; color: var(--muted-foreground); letter-spacing: 0; }}
.msra-stat-note {{ font-size: 12.5px; line-height: 1.45; color: var(--muted-foreground); margin-top: 6px; }}
.msra-stat-delta {{ font-size: 12.5px; font-weight: 600; margin-top: 6px; }}
.msra-stat-delta.is-up {{ color: var(--accent-text); }}
.msra-stat-delta.is-down {{ color: var(--destructive); }}
.msra-stat-delta.is-flat {{ color: var(--muted-foreground); }}

/* ---------- chips / bars ---------- */
.msra-chip {{
  display: inline-flex; align-items: center; gap: 5px;
  border-radius: 999px; padding: 2px 9px;
  font-size: 11px; font-weight: 600; letter-spacing: 0.01em;
  border: 1px solid var(--border);
  background: var(--secondary); color: var(--foreground);
  white-space: nowrap;
}}
.msra-chip.is-ok {{ background: var(--ok-bg); color: var(--accent-text); border-color: #cfdcc8; }}
.msra-chip.is-warn {{ background: var(--warn-bg); color: var(--warn-text); border-color: #ecd9b6; }}
.msra-chip.is-danger {{ background: var(--danger-bg); color: var(--destructive); border-color: #f2cfcd; }}
.msra-chip.is-info {{ background: var(--info-bg); color: #2f4a55; border-color: #d3dee3; }}
.msra-chip .msra-dot {{ background: currentColor; }}

.msra-bar {{ height: 6px; background: var(--muted); border-radius: 999px; overflow: hidden; margin-top: 8px; }}
.msra-bar > span {{ display: block; height: 100%; width: var(--value, 0%); background: var(--accent); border-radius: 999px; }}
.msra-bar.is-warn > span {{ background: #b98218; }}
.msra-bar.is-danger > span {{ background: var(--destructive); }}

/* ---------- bag cards ---------- */
.msra-bag {{
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--card);
  padding: 12px 14px;
  margin-bottom: 10px;
}}
.msra-bag-top {{ display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }}
.msra-bag-code {{ font-size: 14px; font-weight: 600; letter-spacing: -0.01em; }}
.msra-bag-meta {{ font-size: 12px; color: var(--muted-foreground); margin-top: 2px; }}
.msra-bag-figures {{ display: flex; align-items: baseline; justify-content: space-between; gap: 10px; margin-top: 10px; }}
.msra-bag-pct {{ font-size: 1.15rem; font-weight: 600; font-variant-numeric: tabular-nums; }}
.msra-bag-pct small {{ font-size: 0.7rem; color: var(--muted-foreground); font-weight: 500; margin-left: 2px; }}

/* ---------- tables (HTML) ---------- */
.msra-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
.msra-table th {{
  text-align: left; font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase;
  color: var(--muted-foreground); font-weight: 600; padding: 0 10px 8px 0;
  border-bottom: 1px solid var(--border);
}}
.msra-table td {{ padding: 9px 10px 9px 0; border-bottom: 1px solid var(--border); vertical-align: middle; }}
.msra-table tr:last-child td {{ border-bottom: none; }}
.msra-table td.is-num, .msra-table th.is-num {{ text-align: right; font-variant-numeric: tabular-nums; padding-right: 0; }}
.msra-table-wrap {{ overflow-x: auto; }}

/* ---------- threshold strip ---------- */
.msra-strip {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }}
.msra-strip-cell {{
  border: 1px solid var(--border); border-radius: 12px; background: var(--card);
  padding: 10px 12px; min-width: 0;
}}
.msra-strip-room {{ font-size: 13px; font-weight: 600; overflow-wrap: anywhere; }}
.msra-strip-code {{ font-size: 11px; color: var(--muted-foreground); letter-spacing: 0.06em; text-transform: uppercase; }}
.msra-strip-value {{ font-size: 12.5px; margin-top: 6px; display: flex; justify-content: space-between; gap: 8px; }}
.msra-strip-value span:last-child {{ font-variant-numeric: tabular-nums; font-weight: 600; }}

/* ---------- states ---------- */
.msra-empty {{
  border: 1px dashed var(--border);
  border-radius: 14px;
  padding: 20px 18px;
  background: var(--card);
  margin: 8px 0 4px 0;
}}
.msra-empty-title {{ font-size: 14px; font-weight: 600; margin-bottom: 4px; }}
.msra-empty-body {{ font-size: 13px; color: var(--muted-foreground); line-height: 1.5; max-width: 68ch; }}
.msra-gate {{
  border: 1px solid var(--border); border-radius: var(--radius-card);
  background: var(--card); padding: 24px; margin-top: 24px;
}}
.msra-gate-title {{ font-size: 1.1rem; font-weight: 600; }}
.msra-gate-body {{ font-size: 14px; color: var(--muted-foreground); }}

/* ---------- sign-in ---------- */
.msra-signin-brand h1 {{
  font-size: clamp(1.9rem, 1.3rem + 1.6vw, 2.5rem);
  line-height: 1.08; letter-spacing: -0.03em; font-weight: 600; margin: 10px 0 10px 0;
}}
.msra-signin-lede {{ font-size: 15px; line-height: 1.55; color: var(--muted-foreground); max-width: 46ch; }}
.msra-signin-points {{ list-style: none; padding: 0; margin: 22px 0 0 0; display: grid; gap: 12px; }}
.msra-signin-points li {{ display: flex; gap: 10px; align-items: flex-start; font-size: 13.5px; line-height: 1.5; }}
.msra-signin-points .msra-flag-line {{ margin-top: 9px; width: 14px; }}
.msra-signin-points b {{ font-weight: 600; }}
.msra-demo {{
  border: 1px dashed var(--ring);
  border-radius: 12px;
  padding: 10px 12px;
  background: var(--ok-bg);
  font-size: 12.5px;
  line-height: 1.5;
  margin-top: 4px;
}}
.msra-demo-code {{ font-family: ui-monospace, 'SFMono-Regular', Menlo, monospace; font-size: 12.5px; font-weight: 600; }}
.msra-card-head {{ border-bottom: 1px solid var(--border); padding-bottom: 12px; margin-bottom: 14px; }}
.msra-field-error {{
  font-size: 12px;
  font-weight: 600;
  color: var(--destructive);
  margin: 2px 0 8px 0;
}}
.msra-card-title {{ font-size: 1.15rem; font-weight: 600; letter-spacing: -0.01em; margin-top: 6px; }}

/* ---------- sidebar extras ---------- */
.msra-side-brand {{ padding: 0 2px 12px 2px; border-bottom: 1px solid var(--border); margin-bottom: 12px; }}
.msra-side-name {{ font-size: 13.5px; font-weight: 600; }}
.msra-side-sub {{ font-size: 11.5px; color: var(--muted-foreground); margin-top: 2px; }}
.msra-side-user {{
  display: flex; gap: 10px; align-items: center;
  padding: 8px 10px; border: 1px solid var(--border); border-radius: 12px;
  background: var(--background); margin: 10px 0 12px 0;
}}
.msra-avatar {{
  width: 30px; height: 30px; border-radius: 50%;
  background: var(--accent); color: var(--on-accent);
  display: grid; place-items: center; font-size: 12px; font-weight: 600; flex: 0 0 auto;
}}
.msra-side-identity {{ min-width: 0; }}
.msra-side-identity div {{ overflow-wrap: anywhere; }}
.msra-side-label {{ font-size: 10px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted-foreground); font-weight: 600; margin: 14px 0 6px 0; }}

/* ---------- widgets ---------- */
[data-testid^="stBaseButton-"] {{
  font-family: var(--font-body);
  border-radius: var(--radius-control);
  font-weight: 600;
  font-size: 13.5px;
  min-height: 38px;
  border-color: var(--border);
}}
[data-testid^="stBaseButton-"]:focus-visible {{
  outline: 2px solid var(--ring);
  outline-offset: 2px;
}}
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {{
  background: var(--primary);
  border-color: var(--primary);
  color: var(--on-primary);
}}
[data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-primaryFormSubmit"]:hover {{
  background: #26301c;
  border-color: #26301c;
  color: var(--on-primary);
}}
[data-testid^="stBaseButton-"]:hover {{ transform: none; }}
[data-testid^="stBaseButton-"]:active {{ transform: translateY(2px); transition: transform 60ms steps(1); }}

[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div {{
  border-radius: var(--radius-control) !important;
  border-color: var(--border) !important;
  background: var(--card) !important;
  font-family: var(--font-body) !important;
  font-size: 15px !important;
  min-height: 40px;
}}
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within, [data-baseweb="select"] > div:focus-within {{
  border-color: var(--ring) !important;
  box-shadow: 0 0 0 2px rgba(82, 138, 84, 0.25) !important;
}}
input, textarea, select {{ font-family: var(--font-body) !important; font-size: 15px !important; color: var(--foreground); }}
[data-testid="stWidgetLabel"] label p, [data-testid="stWidgetLabel"] p {{
  font-size: 12.5px !important;
  font-weight: 600 !important;
  color: var(--foreground) !important;
}}
[data-testid="stCaptionContainer"] p {{ font-size: 12px; color: var(--muted-foreground); }}
[data-testid="stDataFrame"] {{
  border: 1px solid var(--border);
  border-radius: 14px;
  overflow: hidden;
  background: var(--card);
}}
[data-testid="stAlert"] {{ border-radius: 12px; font-size: 13.5px; }}
[data-testid="stMetric"] {{ background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 12px 14px; }}
[data-testid="stVegaLiteChart"] {{ overflow: hidden; }}
[data-testid="stSegmentedControl"] button {{ font-size: 13px; }}

/* ---------- motion ---------- */
@media (prefers-reduced-motion: reduce) {{
  * {{ transition: none !important; animation: none !important; }}
  [data-testid^="stBaseButton-"]:active {{ transform: none; }}
}}

/* ---------- responsive ---------- */
@media (max-width: 900px) {{
  .msra-strip {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
}}
@media (max-width: 640px) {{
  [data-testid="stMainBlockContainer"], .block-container {{ padding-left: 1rem; padding-right: 1rem; }}
  .msra-head h1 {{ font-size: 1.6rem; }}
  .msra-stat-value {{ font-size: 1.6rem; }}
  .msra-strip {{ grid-template-columns: minmax(0, 1fr); }}
  .msra-topbar {{ padding: 10px 12px; }}
}}
"""


# --------------------------------------------------------------------------
# Page setup
# --------------------------------------------------------------------------
def inject_styles() -> None:
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)


def page_setup(title: str, page_icon: str, *, layout: str = "wide") -> None:
    st.set_page_config(
        page_title=f"{title} · {APP_NAME}",
        page_icon=page_icon,
        layout=layout,
        initial_sidebar_state="expanded",
    )
    inject_styles()


def bootstrap() -> None:
    """Ensure schema + demo data exist on every boot path."""
    db.ensure_ready()


# --------------------------------------------------------------------------
# Chrome
# --------------------------------------------------------------------------
def topbar(context_label: str, meta: Iterable[str] = ()) -> None:
    meta_html = "".join(
        f'<span class="msra-meta-item"><span class="msra-dot"></span>{html.escape(item)}</span>'
        for item in meta
    )
    st.markdown(
        f"""
        <div class="msra-topbar">
          <div class="msra-brand">
            <span class="msra-brand-mark" aria-hidden="true">SR</span>
            <div>
              <div class="msra-brand-name">{html.escape(APP_NAME)}</div>
              <div class="msra-brand-sub">{html.escape(context_label)}</div>
            </div>
          </div>
          <div class="msra-topbar-meta">{meta_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def page_head(eyebrow: str, title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="msra-head">
          <div class="msra-flag"><span class="msra-flag-line" aria-hidden="true"></span>{html.escape(eyebrow)}</div>
          <h1>{html.escape(title)}</h1>
          <p>{html.escape(subtitle)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_head(title: str, flag: str = "", meta: str = "") -> None:
    flag_html = (
        f'<div class="msra-flag"><span class="msra-flag-line" aria-hidden="true"></span>{html.escape(flag)}</div>'
        if flag
        else ""
    )
    meta_html = f'<div class="msra-section-meta">{html.escape(meta)}</div>' if meta else ""
    st.markdown(
        f"""
        <div class="msra-section-head">
          <div>{flag_html}<div class="msra-section-title">{html.escape(title)}</div></div>
          {meta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# Small HTML components
# --------------------------------------------------------------------------
def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def stat_cell(
    label: str,
    value: str,
    unit: str = "",
    note: str = "",
    delta: str = "",
    delta_tone: str = "flat",
) -> str:
    unit_html = f'<span class="msra-stat-unit">{_esc(unit)}</span>' if unit else ""
    note_html = f'<div class="msra-stat-note">{_esc(note)}</div>' if note else ""
    delta_html = (
        f'<div class="msra-stat-delta is-{_esc(delta_tone)}">{_esc(delta)}</div>' if delta else ""
    )
    return (
        '<div class="msra-stat">'
        f'<div class="msra-flag"><span class="msra-flag-line" aria-hidden="true"></span>{_esc(label)}</div>'
        f'<div class="msra-stat-value">{_esc(value)}{unit_html}</div>'
        f"{delta_html}{note_html}"
        "</div>"
    )


def render_stat(
    label: str,
    value: str,
    unit: str = "",
    note: str = "",
    delta: str = "",
    delta_tone: str = "flat",
) -> None:
    st.markdown(
        stat_cell(label, value, unit, note, delta, delta_tone),
        unsafe_allow_html=True,
    )


def chip(text: str, tone: str = "muted") -> str:
    return f'<span class="msra-chip is-{_esc(tone)}"><span class="msra-dot"></span>{_esc(text)}</span>'


def progress_bar(pct: float | None, tone: str = "") -> str:
    value = 0 if pct is None else max(0, min(100, float(pct)))
    tone_class = f" is-{tone}" if tone else ""
    return (
        f'<div class="msra-bar{tone_class}" role="progressbar" aria-valuenow="{value:.0f}" '
        f'aria-valuemin="0" aria-valuemax="100" style="--value:{value:.0f}%">'
        "<span></span></div>"
    )


def empty_state(title: str, body: str) -> None:
    st.markdown(
        f"""
        <div class="msra-empty">
          <div class="msra-empty-title">{_esc(title)}</div>
          <div class="msra-empty-body">{_esc(body)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def query_error(subject: str, error: Exception) -> None:
    """Safe client message + full detail in the server log, with a real retry."""
    logging.getLogger(__name__).exception("failed loading %s", subject, exc_info=error)
    st.error(f"Couldn't load {subject}. The database did not answer as expected.")
    if st.button("Retry", key=f"retry_{abs(hash(subject)) % 10000}"):
        st.rerun()


def is_missing(value: Any) -> bool:
    """True for None, empty text, NaN and NaT - the values that must never render."""
    if value is None or value == "":
        return True
    try:
        return bool(value != value)  # NaN / NaT compare unequal to themselves
    except (TypeError, ValueError):
        return False


def or_dash(value: Any, fallback: str = "—") -> str:
    return fallback if is_missing(value) else str(value)


def render_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    *,
    numeric_columns: Sequence[int] = (),
) -> None:
    """Dense HTML table: real text in the DOM, numeric columns right-aligned."""
    numeric = set(numeric_columns)
    head_cells = "".join(
        f'<th class="is-num">{_esc(head)}</th>' if index in numeric else f"<th>{_esc(head)}</th>"
        for index, head in enumerate(headers)
    )
    body_rows = []
    for row in rows:
        cells = "".join(
            f'<td class="is-num">{_esc(value)}</td>' if index in numeric else f"<td>{_esc(value)}</td>"
            for index, value in enumerate(row)
        )
        body_rows.append(f"<tr>{cells}</tr>")
    st.markdown(
        '<div class="msra-table-wrap"><table class="msra-table">'
        f"<thead><tr>{head_cells}</tr></thead><tbody>{''.join(body_rows)}</tbody>"
        "</table></div>",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# Flash messages (survive the st.rerun() that follows a successful write)
# --------------------------------------------------------------------------
def flash(kind: str, message: str) -> None:
    st.session_state["msra_flash"] = {"kind": kind, "message": message}


def render_flash() -> None:
    item = st.session_state.pop("msra_flash", None)
    if not item:
        return
    renderer = {"success": st.success, "error": st.error, "warning": st.warning}.get(
        item.get("kind", ""), st.info
    )
    renderer(item.get("message", ""))


def navigate(page: str) -> None:
    """Switch pages, degrading to a rerun when the target is not registered.

    The real app registers ``pages/`` and the entry point, so the switch always
    resolves; a bare script run (for example a single-page test harness) does
    not, and a rerun is the safe equivalent there.
    """
    try:
        st.switch_page(page)
    except StreamlitPageNotFoundError:
        logging.getLogger(__name__).info("page %s is not registered in this context", page)
        st.rerun()


# --------------------------------------------------------------------------
# Sidebar: identity, sign out, reset demo data
# --------------------------------------------------------------------------
def sidebar(user: dict[str, Any]) -> None:
    with st.sidebar:
        display_name = user.get("display_name") or user.get("username") or "Operator"
        initials = "".join(part[0] for part in display_name.split()[:2]).upper() or "OP"
        st.markdown(
            f"""
            <div class="msra-side-brand">
              <div class="msra-brand">
                <span class="msra-brand-mark" aria-hidden="true">SR</span>
                <div>
                  <div class="msra-brand-name">{_esc(APP_NAME)}</div>
                  <div class="msra-brand-sub">Grow-run workspace</div>
                </div>
              </div>
            </div>
            <div class="msra-side-user">
              <span class="msra-avatar" aria-hidden="true">{_esc(initials)}</span>
              <div class="msra-side-identity">
                <div class="msra-side-name">{_esc(display_name)}</div>
                <div class="msra-side-sub">{_esc(user.get("email", ""))}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown('<div class="msra-side-label">Session</div>', unsafe_allow_html=True)
        if st.button("Sign out", key="sidebar_sign_out", width="stretch"):
            auth.sign_out()
            navigate(SIGN_IN_PAGE)

        st.markdown('<div class="msra-side-label">Demo data</div>', unsafe_allow_html=True)
        _sidebar_reset_controls()


def _sidebar_reset_controls() -> None:
    if st.session_state.get("confirm_reset"):
        st.warning(
            "Reset wipes every bag, reading, flush and incident, then reseeds the demo dataset.",
            icon="⚠️",
        )
        confirm_col, cancel_col = st.columns(2)
        if confirm_col.button("Reset now", key="sidebar_reset_confirm", type="primary", width="stretch"):
            counts = reset_demo_data()
            db.forget_ready_cache()
            st.session_state["confirm_reset"] = False
            flash(
                "success",
                f"Demo data reset: {counts['grow_rooms']} rooms, {counts['substrate_bags']} bags, "
                f"{counts['colonisation_readings']} readings, {counts['flush_yields']} flushes.",
            )
            st.rerun()
        if cancel_col.button("Cancel", key="sidebar_reset_cancel", width="stretch"):
            st.session_state["confirm_reset"] = False
            st.rerun()
    else:
        if st.button("Reset demo data", key="sidebar_reset", width="stretch"):
            st.session_state["confirm_reset"] = True
            st.rerun()


def signed_in_page(title: str, page_icon: str, *, context_label: str, meta: Iterable[str] = ()) -> dict[str, Any]:
    """Shared bootstrap for every analytics page: setup, gate, chrome, sidebar."""
    page_setup(title, page_icon)
    bootstrap()
    user = auth.require_login()
    topbar(context_label, meta)
    sidebar(user)
    render_flash()
    return user


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------
def fmt_g(value: Any, *, unit: bool = True) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if number >= 1000:
        text = f"{number / 1000:,.2f}"
        return f"{text} kg" if unit else text
    text = f"{number:,.0f}"
    return f"{text} g" if unit else text


def fmt_int(value: Any) -> str:
    try:
        return f"{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return "—"


def human_date(value: Any) -> str:
    if value in (None, ""):
        return "—"
    if isinstance(value, (date, datetime)):
        parsed = value
    else:
        try:
            parsed = date.fromisoformat(str(value)[:10])
        except ValueError:
            return str(value)
    return parsed.strftime("%d %b %Y")


def relative_days(value: Any) -> str:
    if value in (None, ""):
        return "—"
    try:
        parsed = date.fromisoformat(str(value)[:10])
    except ValueError:
        return str(value)
    days = (date.today() - parsed).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    return f"{days} days ago"


# --------------------------------------------------------------------------
# Charts (Altair over pandas; hex colours only)
# --------------------------------------------------------------------------
def style_chart(chart: alt.Chart, *, height: int = 300) -> alt.Chart:
    return (
        chart.properties(height=height)
        .configure(background="#fefffc", font="Lexend, sans-serif", padding=6)
        .configure_axis(
            labelColor=TOKENS["muted-foreground"],
            titleColor=TOKENS["foreground"],
            gridColor=TOKENS["muted"],
            domainColor=TOKENS["border"],
            tickColor=TOKENS["border"],
            labelFontSize=12,
            titleFontSize=12,
            titleFontWeight=600,
            labelFont="Lexend, sans-serif",
            titleFont="Lexend, sans-serif",
        )
        .configure_view(stroke=None)
        .configure_legend(
            labelColor=TOKENS["muted-foreground"],
            titleColor=TOKENS["foreground"],
            labelFontSize=12,
            titleFontSize=12,
            orient="top",
            direction="horizontal",
            labelFont="Lexend, sans-serif",
        )
    )


def show_chart(chart: alt.Chart, *, height: int = 300, key: str | None = None) -> None:
    st.altair_chart(
        style_chart(chart, height=height),
        width="stretch",
        theme=None,
        key=key,
    )
