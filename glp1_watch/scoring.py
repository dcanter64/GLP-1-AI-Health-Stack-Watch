from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

MAX_SCORING_STORIES_PER_PRIMARY_TICKER = 4
MAX_SCORING_STORIES_PER_PRIMARY_TICKER_THEME = 2


@dataclass
class ScoreSnapshot:
    overall_score: float
    stance: str
    lly_ai_trade_score: float
    component_scores: pd.DataFrame
    lly_ai_trade_components: pd.DataFrame


def clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def scaled_score(value: float, bear: float, bull: float) -> float:
    if pd.isna(value) or not np.isfinite(float(value)):
        return 0.0
    if bull == bear:
        return 50.0
    return clamp((value - bear) / (bull - bear) * 100.0)


def stance_from_score(score: float) -> str:
    if score >= 80:
        return "Strong Bullish"
    if score >= 60:
        return "Bullish"
    if score >= 40:
        return "Neutral"
    if score >= 20:
        return "Caution"
    return "Bearish"


def qualified_scoring_articles(articles_df: pd.DataFrame) -> pd.DataFrame:
    if articles_df.empty:
        return articles_df.copy()

    qualified = articles_df[articles_df["theme"] != "Other"].copy()
    if qualified.empty:
        return qualified

    if "published_at" not in qualified.columns:
        qualified["published_at"] = pd.NaT
    qualified["published_at"] = pd.to_datetime(qualified["published_at"], utc=True, errors="coerce")
    if "relevance_score" not in qualified.columns:
        qualified["relevance_score"] = 0.0
    if "tickers" not in qualified.columns:
        qualified["tickers"] = ""
    if "target_ticker" not in qualified.columns:
        qualified["target_ticker"] = ""
    qualified["primary_ticker"] = qualified["tickers"].fillna("").astype(str).str.split(r",\s*").str[0]
    qualified.loc[qualified["primary_ticker"] == "", "primary_ticker"] = (
        qualified["target_ticker"].fillna("").astype(str)
    )
    qualified.loc[qualified["primary_ticker"] == "", "primary_ticker"] = "UNSPECIFIED"
    qualified = qualified.sort_values(
        ["relevance_score", "published_at"],
        ascending=[False, False],
        na_position="last",
    )

    diversified = (
        qualified.groupby(["primary_ticker", "theme"], group_keys=False)
        .head(MAX_SCORING_STORIES_PER_PRIMARY_TICKER_THEME)
    )
    return (
        diversified.groupby("primary_ticker", group_keys=False)
        .head(MAX_SCORING_STORIES_PER_PRIMARY_TICKER)
        .reset_index(drop=True)
    )


def _optional_finite_float(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if np.isfinite(parsed) else None


def _scaled_or_zero(value: object, bear: float, bull: float) -> float:
    parsed = _optional_finite_float(value)
    return 0.0 if parsed is None else scaled_score(parsed, bear, bull)


def _bool_or_false(value: object) -> bool:
    try:
        return False if pd.isna(value) else bool(value)
    except (TypeError, ValueError):
        return False


def _lly_nvo_pair_score(lly: pd.Series, nvo: pd.Series) -> tuple[float, str]:
    lly_return = _optional_finite_float(lly.get("return_3m"))
    nvo_return = _optional_finite_float(nvo.get("return_3m"))
    broad_rs = [
        _optional_finite_float(lly.get("rs_vs_xlv")),
        _optional_finite_float(lly.get("rs_vs_qqq")),
        _optional_finite_float(lly.get("rs_vs_spy")),
    ]
    if lly_return is None or nvo_return is None:
        return 0.0, "Unavailable because one or both 3M returns are missing."
    pair_score = scaled_score(lly_return - nvo_return, -0.2, 0.2)
    if all(value is not None and value < 0 for value in broad_rs):
        return min(pair_score, 50.0), "Capped at neutral because LLY trails XLV, QQQ, and SPY."
    return pair_score, "Pair-relative evidence only."


def compute_lly_ai_trade_components(
    performance_table: pd.DataFrame,
    articles_df: pd.DataFrame,
) -> pd.DataFrame:
    """Return an auditable component breakdown for the LLY AI-trade score.

    Pair-relative strength versus NVO is capped at neutral when LLY trails
    XLV, QQQ, and SPY. Beating a weaker peer is useful context, but it must
    not masquerade as broad market confirmation.
    """
    columns = ["component", "score", "max_points", "contribution", "note"]
    if performance_table.empty or "ticker" not in performance_table.columns:
        return pd.DataFrame(columns=columns)

    lly = performance_table.loc[performance_table["ticker"] == "LLY"].squeeze()
    if lly.empty:
        return pd.DataFrame(columns=columns)

    rows: list[tuple[str, float, float, float, str]] = []

    def add(component: str, score: float, max_points: float, note: str = "") -> None:
        bounded = clamp(score)
        rows.append(
            (component, round(bounded, 1), max_points, round(bounded * max_points / 100.0, 1), note)
        )

    # The component budget is exactly 100 points.  Missing components remain
    # visible at zero rather than being omitted or implicitly renormalized.
    add("Above 50DMA", 100.0 if _bool_or_false(lly.get("above_50dma")) else 0.0, 10.0)
    add("Above 200DMA", 100.0 if _bool_or_false(lly.get("above_200dma")) else 0.0, 10.0)
    add("3M price momentum", _scaled_or_zero(lly.get("return_3m"), -0.2, 0.3), 15.0)
    add(
        "Distance from 52-week high",
        _scaled_or_zero(lly.get("distance_from_52w_high"), -0.4, 0.0),
        15.0,
    )
    add("Relative strength vs XLV", _scaled_or_zero(lly.get("rs_vs_xlv"), -0.15, 0.15), 10.0)
    add("Relative strength vs QQQ", _scaled_or_zero(lly.get("rs_vs_qqq"), -0.15, 0.15), 10.0)

    nvo_row = performance_table.loc[performance_table["ticker"] == "NVO"]
    if not nvo_row.empty:
        pair_score, note = _lly_nvo_pair_score(lly, nvo_row.iloc[0])
        add("LLY vs NVO pair-relative strength", pair_score, 10.0, note)
    else:
        add(
            "LLY vs NVO pair-relative strength",
            0.0,
            10.0,
            "Unavailable because NVO 3M return is missing.",
        )

    scoring_articles = qualified_scoring_articles(articles_df)
    if not scoring_articles.empty:
        lly_news = scoring_articles[scoring_articles["tickers"].str.contains("LLY", na=False)]
        add("Qualified LLY news volume", scaled_score(len(lly_news), 0, 25), 10.0)
        add(
            "Qualified LLY news sentiment",
            scaled_score(lly_news["sentiment_score"].mean() if not lly_news.empty else 0.0, -0.5, 0.5),
            10.0,
        )
    else:
        add("Qualified LLY news volume", 0.0, 10.0, "No qualified LLY news.")
        add("Qualified LLY news sentiment", 0.0, 10.0, "No qualified LLY news.")

    return pd.DataFrame(rows, columns=columns)


def compute_lly_ai_trade_score(performance_table: pd.DataFrame, articles_df: pd.DataFrame) -> float:
    components = compute_lly_ai_trade_components(performance_table, articles_df)
    if components.empty:
        return 0.0
    return round(clamp(float(components["contribution"].sum())), 1)


def compute_component_scores(performance_table: pd.DataFrame, articles_df: pd.DataFrame) -> pd.DataFrame:
    if performance_table.empty or "ticker" not in performance_table.columns:
        component_scores = pd.DataFrame(
            [
                ("LLY price momentum", 0.0, 0.15),
                ("LLY relative strength vs XLV", 0.0, 0.1),
                ("LLY vs NVO pair-relative strength", 0.0, 0.1),
                ("GLP-1 news volume", 0.0, 0.08),
                ("Positive GLP-1 sentiment", 50.0 if not articles_df.empty else 0.0, 0.08),
                ("AI-biotech news volume", 0.0, 0.08),
                ("Positive AI-biotech sentiment", 50.0 if not articles_df.empty else 0.0, 0.08),
                ("M&A / partnership activity", 0.0, 0.08),
                ("Pipeline / regulatory catalysts", 0.0, 0.07),
                ("Biotech risk appetite", 0.0, 0.09),
                ("AI infrastructure confirmation", 0.0, 0.09),
            ],
            columns=["component", "score", "weight"],
        )
        component_scores["weighted_score"] = component_scores["score"] * component_scores["weight"]
        return component_scores

    performance_indexed = performance_table.set_index("ticker")
    lly = performance_indexed.loc["LLY"] if "LLY" in performance_indexed.index else pd.Series(dtype=float)

    scoring_articles = qualified_scoring_articles(articles_df)
    themes = scoring_articles["theme"].value_counts() if not scoring_articles.empty else pd.Series(dtype=float)
    sentiment_mean = float(scoring_articles["sentiment_score"].mean()) if not scoring_articles.empty else 0.0

    glp1_news = int(themes.get("GLP-1 Demand", 0) + themes.get("GLP-1 Competition", 0))
    ai_biotech_news = int(themes.get("AI Drug Discovery", 0) + themes.get("Lilly AI Infrastructure", 0))
    ma_partnership_news = int(themes.get("Lilly M&A / IP Acquisition", 0))
    catalyst_news = int(themes.get("Regulatory Risk", 0) + themes.get("Manufacturing / Supply", 0))

    xbi_return = float(performance_indexed.loc["XBI"]["return_3m"]) if "XBI" in performance_indexed.index else 0.0
    ibb_return = float(performance_indexed.loc["IBB"]["return_3m"]) if "IBB" in performance_indexed.index else 0.0
    nvda_return = float(performance_indexed.loc["NVDA"]["return_3m"]) if "NVDA" in performance_indexed.index else 0.0
    smh_return = float(performance_indexed.loc["SMH"]["return_3m"]) if "SMH" in performance_indexed.index else 0.0
    soxx_return = float(performance_indexed.loc["SOXX"]["return_3m"]) if "SOXX" in performance_indexed.index else 0.0

    component_rows = [
        ("LLY price momentum", scaled_score(float(lly.get("return_3m", 0.0)), -0.2, 0.3), 0.15),
        ("LLY relative strength vs XLV", scaled_score(float(lly.get("rs_vs_xlv", 0.0)), -0.15, 0.15), 0.1),
        (
            "LLY vs NVO pair-relative strength",
            _lly_nvo_pair_score(lly, performance_indexed.loc["NVO"])[0]
            if "NVO" in performance_indexed.index
            else 0.0,
            0.1,
        ),
        ("GLP-1 news volume", scaled_score(glp1_news, 0, 40), 0.08),
        ("Positive GLP-1 sentiment", scaled_score(sentiment_mean, -0.4, 0.4), 0.08),
        ("AI-biotech news volume", scaled_score(ai_biotech_news, 0, 30), 0.08),
        ("Positive AI-biotech sentiment", scaled_score(sentiment_mean, -0.4, 0.4), 0.08),
        ("M&A / partnership activity", scaled_score(ma_partnership_news, 0, 12), 0.08),
        ("Pipeline / regulatory catalysts", scaled_score(catalyst_news, 0, 12), 0.07),
        ("Biotech risk appetite", scaled_score(np.mean([xbi_return, ibb_return]), -0.2, 0.25), 0.09),
        ("AI infrastructure confirmation", scaled_score(np.mean([nvda_return, smh_return, soxx_return]), -0.15, 0.3), 0.09),
    ]

    component_scores = pd.DataFrame(component_rows, columns=["component", "score", "weight"])
    component_scores["weighted_score"] = component_scores["score"] * component_scores["weight"]
    return component_scores


def compute_score_snapshot(performance_table: pd.DataFrame, articles_df: pd.DataFrame) -> ScoreSnapshot:
    component_scores = compute_component_scores(performance_table, articles_df)
    overall_score = round(component_scores["weighted_score"].sum(), 1)
    stance = stance_from_score(overall_score)
    lly_ai_trade_components = compute_lly_ai_trade_components(performance_table, articles_df)
    lly_ai_trade_score = (
        round(clamp(float(lly_ai_trade_components["contribution"].sum())), 1)
        if not lly_ai_trade_components.empty
        else 0.0
    )
    return ScoreSnapshot(
        overall_score=overall_score,
        stance=stance,
        lly_ai_trade_score=lly_ai_trade_score,
        component_scores=component_scores,
        lly_ai_trade_components=lly_ai_trade_components,
    )


