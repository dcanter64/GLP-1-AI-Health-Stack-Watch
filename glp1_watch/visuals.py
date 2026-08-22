from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .market_data import extract_close_prices


def line_chart(series_map: dict[str, pd.Series], title: str) -> go.Figure:
    fig = go.Figure()
    for name, series in series_map.items():
        base = series.dropna().iloc[0] if not series.dropna().empty else 1.0
        normalized = series / base * 100.0
        fig.add_trace(go.Scatter(x=normalized.index, y=normalized.values, mode="lines", name=name))
    fig.update_layout(title=title, yaxis_title="Indexed to 100", xaxis_title="")
    return fig


def lly_relative_chart(price_history: pd.DataFrame, comparator: str) -> go.Figure:
    close = extract_close_prices(price_history)
    subset = close[[col for col in ["LLY", comparator] if col in close.columns]].dropna()
    return line_chart(
        {ticker: subset[ticker] for ticker in subset.columns},
        f"LLY vs {comparator}",
    )


def lly_price_chart(price_history: pd.DataFrame) -> go.Figure:
    close = extract_close_prices(price_history)
    series = close["LLY"].dropna()
    fig = go.Figure(go.Scatter(x=series.index, y=series.values, mode="lines", name="LLY"))
    fig.update_layout(title="LLY Price", yaxis_title="Price", xaxis_title="")
    return fig


def performance_heatmap(performance_table: pd.DataFrame, groups: list[str]) -> go.Figure:
    subset = performance_table[performance_table["group"].isin(groups)].copy()
    subset = subset.sort_values(["group", "ticker"])
    metric_cols = ["return_5d", "return_1m", "return_3m", "return_6m", "return_ytd"]
    heatmap = px.imshow(
        subset[metric_cols].mul(100).round(1),
        x=metric_cols,
        y=subset["ticker"],
        color_continuous_scale="RdYlGn",
        aspect="auto",
        title="Performance Heatmap (%)",
        text_auto=True,
    )
    return heatmap


def theme_bar_chart(theme_summary: pd.DataFrame) -> go.Figure:
    if theme_summary.empty:
        return go.Figure()
    fig = px.bar(
        theme_summary.sort_values("story_count", ascending=False),
        x="story_count",
        y="theme",
        color="avg_sentiment",
        orientation="h",
        color_continuous_scale="RdYlGn",
        title="Theme Scoreboard",
    )
    return fig


def component_score_chart(component_scores: pd.DataFrame) -> go.Figure:
    fig = px.bar(
        component_scores,
        x="weighted_score",
        y="component",
        orientation="h",
        color="score",
        color_continuous_scale="RdYlGn",
        title="Flywheel Components",
    )
    return fig
