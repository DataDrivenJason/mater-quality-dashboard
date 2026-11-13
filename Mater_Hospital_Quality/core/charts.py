"""Plotly figures: the control chart and the equity interval plot."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from . import spc

BLUE = "#2a78d6"        # the data
INK = "#52514e"         # centre line, limits
MUTED = "#898781"
IMPROVE = "#2a78d6"     # Making Data Count: blue = improvement
CONCERN = "#ec835a"     # orange = concern
NEUTRAL = "#7b5cc4"     # purple = change with no good direction
GRID = "#e6e4de"


def fmt(value, unit: str) -> str:
    """A value as a reader expects to see it."""
    if value is None or not np.isfinite(value):
        return "No data"
    if unit == "%":
        return f"{value:.1f}%"
    if unit == "time of day":
        h = int(value) % 24
        m = int(round((value - int(value)) * 60))
        if m == 60:
            h, m = (h + 1) % 24, 0
        return f"{h:02d}:{m:02d}"
    if unit == "€":
        return f"€{value:,.0f}"
    if unit == "minutes":
        return f"{value:.0f} min"
    if unit == "days":
        return f"{value:.1f} days" if value % 1 else f"{value:.0f} days"
    if unit == "doses":
        if value % 1:
            return f"{value:.1f} doses"
        return "1 dose" if value == 1 else f"{value:.0f} doses"
    if unit == "score /10":
        return f"{value:.1f} / 10"
    return f"{value:,.1f}" if value % 1 else f"{value:,.0f}"


def _layout(height: int, title: str, ytitle: str) -> dict:
    return dict(
        height=height, title=dict(text=title, font=dict(size=14)),
        margin=dict(l=10, r=10, t=40 if title else 10, b=10),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified", showlegend=False,
        xaxis=dict(showgrid=False, tickformat="%b %Y"),
        yaxis=dict(title=ytitle, gridcolor=GRID, zeroline=False),
        font=dict(size=12),
    )


def control_chart(res: spc.ChartResult, title: str = "", height: int = 280) -> go.Figure:
    f = res.frame.copy()
    f["x"] = pd.to_datetime(f["x"])
    unit = res.unit
    hover_val = [fmt(v, unit) for v in f["value"]]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=f["x"], y=f["ucl"], mode="lines", name="Upper limit",
                             line=dict(color=MUTED, width=1, dash="dash"), hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=f["x"], y=f["lcl"], mode="lines", name="Lower limit",
                             line=dict(color=MUTED, width=1, dash="dash"), hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=f["x"], y=f["cl"], mode="lines", name="Average",
                             line=dict(color=INK, width=1.2), hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=f["x"], y=f["value"], mode="lines+markers", name="This month",
                             line=dict(color=BLUE, width=2), marker=dict(size=6, color=BLUE),
                             text=hover_val, hovertemplate="%{text}<extra></extra>",
                             connectgaps=False))
    sig = f[f["special"].astype(bool) & f["value"].notna()]
    if len(sig):
        hib = res.higher_is_better
        colours = []
        for d in sig["special_dir"]:
            if hib is None or d == 0:
                colours.append(NEUTRAL)
            else:
                colours.append(IMPROVE if (d > 0) == hib else CONCERN)
        fig.add_trace(go.Scatter(x=sig["x"], y=sig["value"], mode="markers", name="Signal",
                                 marker=dict(size=12, symbol="diamond", color=colours,
                                             line=dict(color="white", width=1)),
                                 hoverinfo="skip"))
    if res.target is not None:
        fig.add_hline(y=res.target, line=dict(color=INK, width=1.5, dash="dot"),
                      annotation_text=f"Target {fmt(res.target, unit)}",
                      annotation_position="top left", annotation_font_size=10)
    ytitle = {"time of day": "Hour of day", "€": "€", "%": "%"}.get(unit, unit)
    fig.update_layout(**_layout(height, title, ytitle))
    return fig


def equity_plot(rows: pd.DataFrame, overall: float, unit: str, title: str = "") -> go.Figure:
    """Each subgroup's value with its 95% interval, against the overall figure.
    Flagged groups are diamonds as well as coloured, so it reads in greyscale."""
    r = rows.copy()
    r["label"] = [f"{g} ({d.lower()})" for d, g in zip(r["dimension"], r["group"])]
    order = list(r["label"])
    fig = go.Figure()
    fig.add_vline(x=overall, line=dict(color=INK, width=1.5))
    style = {"worse": (CONCERN, "diamond", 13), "better": (IMPROVE, "diamond", 13),
             "different": (NEUTRAL, "diamond", 13), "no clear difference": (MUTED, "circle", 9)}
    for status, (colour, symbol, size) in style.items():
        sub = r[(r["status"] == status) & r["value"].notna()]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["value"], y=sub["label"], mode="markers", name=status.capitalize(),
            marker=dict(color=colour, symbol=symbol, size=size, line=dict(color="white", width=1)),
            error_x=dict(type="data", symmetric=False,
                         array=(sub["hi"] - sub["value"]).clip(lower=0),
                         arrayminus=(sub["value"] - sub["lo"]).clip(lower=0),
                         color=colour, thickness=1.6, width=0),
            customdata=np.stack([sub["n"], sub["lo"], sub["hi"], sub["q"]], axis=-1),
            hovertemplate=("<b>%{y}</b><br>%{x:.3~f} (95% CI %{customdata[1]:.3~f} to "
                           "%{customdata[2]:.3~f})<br>%{customdata[0]:,.0f} patients, "
                           "q = %{customdata[3]:.3f}<extra></extra>")))
    hidden = r[r["status"] == "suppressed"]
    if not hidden.empty:
        fig.add_trace(go.Scatter(x=[overall] * len(hidden), y=hidden["label"], mode="text",
                                 text=["hidden (too few patients)"] * len(hidden), textposition="middle right",
                                 textfont=dict(size=10.5, color=MUTED), hoverinfo="skip"))
    lay = _layout(110 + 28 * len(order), title, "")
    lay["hovermode"] = "closest"
    lay["showlegend"] = True
    lay["legend"] = dict(orientation="h", y=-0.15)
    lay["xaxis"] = dict(title=unit, gridcolor=GRID, showgrid=True)
    lay["yaxis"] = dict(categoryorder="array", categoryarray=order[::-1], showgrid=False)
    fig.update_layout(**lay)
    return fig
