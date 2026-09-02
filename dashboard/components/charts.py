"""Plotly charts — restrained, dark, semantic colour. No chart junk."""
from __future__ import annotations

import plotly.graph_objects as go

from dashboard import theme as T

_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", size=11, color=T.T1),
    margin=dict(l=6, r=6, t=6, b=6),
    legend=dict(font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
)


def _layout(**over) -> dict:
    d = {k: v for k, v in _LAYOUT.items()}
    d.update(over)
    return d


def donut(data: dict[str, int], center_label: str = "Total",
          palette: dict[str, str] | None = None, height: int = 210) -> go.Figure:
    labels = list(data.keys())
    values = list(data.values())
    total = sum(values)
    colors = [(palette or {}).get(l, T.ACCENT) for l in labels]
    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.68, sort=False,
        marker=dict(colors=colors, line=dict(color=T.BG, width=2)),
        textinfo="none",
        hovertemplate="%{label}: %{value} (%{percent})<extra></extra>",
    ))
    fig.update_layout(
        **_layout(height=height, showlegend=False),
        annotations=[dict(text=f"<b>{total}</b><br><span style='font-size:9px'>{center_label}</span>",
                          x=0.5, y=0.5, showarrow=False,
                          font=dict(size=20, color=T.T0))],
    )
    return fig


def stacked_bars(days: list[dict], height: int = 200) -> go.Figure:
    x = [d["acq_date"][5:] for d in days]
    series = [("critical", T.CRIT), ("high", T.HIGH), ("medium", T.MED), ("low", T.LOW)]
    fig = go.Figure()
    for key, col in series:
        fig.add_bar(x=x, y=[int(d.get(key) or 0) for d in days], name=key.title(),
                    marker_color=col, marker_line_width=0)
    totals = [int(d.get("detections") or 0) for d in days]
    fig.update_layout(**_layout(
        height=height, barmode="stack",
        xaxis=dict(showgrid=False, tickfont=dict(size=10)),
        yaxis=dict(showgrid=True, gridcolor=T.BORDER, zeroline=False, tickfont=dict(size=9)),
        legend=dict(orientation="h", y=-0.28, x=0, font=dict(size=9)),
        bargap=0.45,
    ))
    fig.update_traces(hovertemplate="%{y}<extra>%{fullData.name}</extra>")
    for xi, ti in zip(x, totals):
        fig.add_annotation(x=xi, y=ti, text=str(ti), showarrow=False, yshift=9,
                           font=dict(size=9, color=T.T1))
    return fig


def hbar(data: dict[str, int], color: str = T.ACCENT, height: int = 220) -> go.Figure:
    items = list(data.items())[::-1]
    fig = go.Figure(go.Bar(
        x=[v for _, v in items], y=[k for k, _ in items], orientation="h",
        marker_color=color, marker_line_width=0,
        hovertemplate="%{y}: %{x}<extra></extra>",
    ))
    fig.update_layout(**_layout(
        height=height,
        xaxis=dict(showgrid=True, gridcolor=T.BORDER, zeroline=False, tickfont=dict(size=9)),
        yaxis=dict(showgrid=False, tickfont=dict(size=10)),
        bargap=0.4,
    ))
    return fig
