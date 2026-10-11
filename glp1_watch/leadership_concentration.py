"""Phase 1: sleeve-level market structure and leadership concentration.

Sleeve summaries are built from the existing performance table (no new data
fetching). Concentration analysis then measures whether positive market
evidence is broad, selective, or leader-dependent.

Breadth counts (percent above moving averages, percent outperforming
benchmarks) are calculated from the seven required sleeves only, so the
supporting AI Infrastructure Enablers sleeve cannot make weak healthcare
breadth look healthy.
"""

from __future__ import annotations

import pandas as pd

from .health_stack_sleeves import Sleeve, core_breadth_tickers, required_sleeves

LEADER_SLEEVE_NAME = "Established GLP-1 Leaders"

SLEEVE_STATUS_CONFIRMING = "confirming"
SLEEVE_STATUS_MIXED = "mixed"
SLEEVE_STATUS_DETERIORATING = "deteriorating"
SLEEVE_STATUS_INSUFFICIENT = "insufficient data"

CONCENTRATION_BROAD = "broad"
CONCENTRATION_SELECTIVE = "selective"
CONCENTRATION_LEADER_DEPENDENT = "leader-dependent"
CONCENTRATION_INSUFFICIENT = "insufficient data"

#: A sleeve needs at least this share of names with usable 3M returns,
#: otherwise its status is "insufficient data" instead of a guess.
MIN_SLEEVE_COVERAGE = 0.5


def _usable_returns(frame: pd.DataFrame) -> pd.Series:
    if frame.empty or "return_3m" not in frame.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(frame["return_3m"], errors="coerce").dropna()


def _share_true(frame: pd.DataFrame, column: str) -> float:
    """Share of True values; NaN when the column is missing or has no usable values."""
    if frame.empty or column not in frame.columns:
        return float("nan")
    values = frame[column].dropna()
    if values.empty:
        return float("nan")
    return float(values.astype(bool).mean())


def _outperform_share(frame: pd.DataFrame, column: str) -> tuple[float, int]:
    """Share of names with usable values outperforming (> 0); plus usable count.

    Returns NaN (not 0.0) when there is nothing usable to measure, so callers
    cannot mistake missing data for measured weakness.
    """
    if frame.empty or column not in frame.columns:
        return float("nan"), 0
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    if values.empty:
        return float("nan"), 0
    return float((values > 0).mean()), int(len(values))


def _sleeve_status(coverage: float, outperform_xlv_share: float, avg_return_3m: float) -> str:
    if coverage < MIN_SLEEVE_COVERAGE:
        return SLEEVE_STATUS_INSUFFICIENT
    if pd.isna(outperform_xlv_share):
        # Relative-strength data is structural to confirmation; without it we
        # report insufficient data rather than a fabricated signal.
        return SLEEVE_STATUS_INSUFFICIENT
    if outperform_xlv_share >= 0.6 and avg_return_3m > 0:
        return SLEEVE_STATUS_CONFIRMING
    if outperform_xlv_share <= 0.4 and avg_return_3m < 0:
        return SLEEVE_STATUS_DETERIORATING
    return SLEEVE_STATUS_MIXED


def build_sleeve_summaries(performance_table: pd.DataFrame, sleeves: list[Sleeve]) -> pd.DataFrame:
    """One row per sleeve with market-structure statistics.

    Adds no new data: every metric derives from the existing performance
    table. Sleeves with too little usable data get status "insufficient data"
    rather than a fabricated signal.
    """
    columns = [
        "sleeve",
        "required",
        "ticker_count",
        "names_with_data",
        "coverage",
        "avg_return_3m",
        "pct_outperform_xlv",
        "pct_outperform_spy",
        "pct_above_50dma",
        "pct_above_200dma",
        "best_ticker",
        "best_return_3m",
        "worst_ticker",
        "worst_return_3m",
        "status",
    ]
    if not sleeves:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, object]] = []
    for sleeve in sleeves:
        subset = (
            performance_table[performance_table["ticker"].isin(sleeve.tickers)]
            if not performance_table.empty
            else performance_table
        )
        returns = _usable_returns(subset)
        names_with_data = int(len(returns))
        ticker_count = len(sleeve.tickers)
        coverage = names_with_data / ticker_count if ticker_count else 0.0

        if names_with_data == 0:
            rows.append(
                {
                    "sleeve": sleeve.name,
                    "required": sleeve.required,
                    "ticker_count": ticker_count,
                    "names_with_data": 0,
                    "coverage": 0.0,
                    "avg_return_3m": float("nan"),
                    "pct_outperform_xlv": 0.0,
                    "pct_outperform_spy": 0.0,
                    "pct_above_50dma": 0.0,
                    "pct_above_200dma": 0.0,
                    "best_ticker": None,
                    "best_return_3m": float("nan"),
                    "worst_ticker": None,
                    "worst_return_3m": float("nan"),
                    "status": SLEEVE_STATUS_INSUFFICIENT,
                }
            )
            continue

        outperform_xlv, _ = _outperform_share(subset, "rs_vs_xlv")
        outperform_spy, _ = _outperform_share(subset, "rs_vs_spy")
        avg_return = float(returns.mean())
        # returns is indexed by the performance-table index; map back to tickers.
        tickers_by_index = subset.loc[returns.index, "ticker"]
        best_ticker = str(tickers_by_index.loc[returns.idxmax()])
        worst_ticker = str(tickers_by_index.loc[returns.idxmin()])

        rows.append(
            {
                "sleeve": sleeve.name,
                "required": sleeve.required,
                "ticker_count": ticker_count,
                "names_with_data": names_with_data,
                "coverage": round(coverage, 3),
                "avg_return_3m": round(avg_return, 4),
                "pct_outperform_xlv": round(outperform_xlv, 3),
                "pct_outperform_spy": round(outperform_spy, 3),
                "pct_above_50dma": round(_share_true(subset, "above_50dma"), 3),
                "pct_above_200dma": round(_share_true(subset, "above_200dma"), 3),
                "best_ticker": best_ticker,
                "best_return_3m": round(float(returns.max()), 4),
                "worst_ticker": worst_ticker,
                "worst_return_3m": round(float(returns.min()), 4),
                "status": _sleeve_status(coverage, outperform_xlv, avg_return),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def compute_leadership_concentration(
    performance_table: pd.DataFrame,
    sleeve_summaries: pd.DataFrame,
    sleeves: list[Sleeve],
) -> dict[str, object]:
    """Measure whether positive market evidence is broad or concentrated.

    Returns a dict with sleeve counts, breadth shares (required sleeves
    only), top-name contribution shares, the LLY contribution versus the core
    mean, and a verdict of "broad", "selective", "leader-dependent", or
    "insufficient data".
    """
    result: dict[str, object] = {
        "verdict": CONCENTRATION_INSUFFICIENT,
        "confirming_sleeves": [],
        "deteriorating_sleeves": [],
        "confirming_count": 0,
        "deteriorating_count": 0,
        "strongest_sleeve": None,
        "weakest_sleeve": None,
        "leader_sleeve_status": SLEEVE_STATUS_INSUFFICIENT,
        "top1_share": 0.0,
        "top3_share": 0.0,
        "lly_contribution": None,
        "pct_above_50dma": 0.0,
        "pct_above_200dma": 0.0,
        "pct_outperform_xlv": 0.0,
        "pct_outperform_spy": 0.0,
        "core_names_with_data": 0,
    }

    required_names = [sleeve.name for sleeve in required_sleeves(sleeves)]
    if not sleeve_summaries.empty:
        req = sleeve_summaries[sleeve_summaries["sleeve"].isin(required_names)]
        result["confirming_sleeves"] = req[req["status"] == SLEEVE_STATUS_CONFIRMING]["sleeve"].tolist()
        result["deteriorating_sleeves"] = req[req["status"] == SLEEVE_STATUS_DETERIORATING]["sleeve"].tolist()
        result["confirming_count"] = int(len(result["confirming_sleeves"]))
        result["deteriorating_count"] = int(len(result["deteriorating_sleeves"]))
        with_data = req[req["status"] != SLEEVE_STATUS_INSUFFICIENT]
        if not with_data.empty:
            result["strongest_sleeve"] = str(with_data.sort_values("avg_return_3m", ascending=False).iloc[0]["sleeve"])
            result["weakest_sleeve"] = str(with_data.sort_values("avg_return_3m", ascending=True).iloc[0]["sleeve"])
        leader_rows = req[req["sleeve"] == LEADER_SLEEVE_NAME]
        if not leader_rows.empty:
            result["leader_sleeve_status"] = str(leader_rows.iloc[0]["status"])

    core_tickers = core_breadth_tickers(sleeves)
    core = (
        performance_table[performance_table["ticker"].isin(core_tickers)]
        if not performance_table.empty
        else performance_table
    )
    core_returns = _usable_returns(core)
    result["core_names_with_data"] = int(len(core_returns))
    if core_returns.empty:
        return result

    positive = core_returns[core_returns > 0]
    positive_sum = float(positive.sum())
    if positive_sum > 0:
        result["top1_share"] = round(float(positive.max()) / positive_sum, 3)
        result["top3_share"] = round(float(positive.nlargest(3).sum()) / positive_sum, 3)

    core_mean = float(core_returns.mean())
    if not core.empty and "LLY" in core["ticker"].values:
        lly_return = pd.to_numeric(
            core.loc[core["ticker"] == "LLY", "return_3m"], errors="coerce"
        ).dropna()
        if not lly_return.empty:
            result["lly_contribution"] = round(float(lly_return.iloc[0]) - core_mean, 4)

    result["pct_above_50dma"] = round(_share_true(core, "above_50dma"), 3)
    result["pct_above_200dma"] = round(_share_true(core, "above_200dma"), 3)
    outperform_xlv, _ = _outperform_share(core, "rs_vs_xlv")
    outperform_spy, _ = _outperform_share(core, "rs_vs_spy")
    result["pct_outperform_xlv"] = round(outperform_xlv, 3)
    result["pct_outperform_spy"] = round(outperform_spy, 3)

    confirming_count = int(result["confirming_count"])
    leader_confirming = result["leader_sleeve_status"] == SLEEVE_STATUS_CONFIRMING
    if leader_confirming and confirming_count <= 2:
        verdict = CONCENTRATION_LEADER_DEPENDENT
    elif float(result["top1_share"]) >= 0.5:
        verdict = CONCENTRATION_LEADER_DEPENDENT
    elif confirming_count >= 4 and float(result["top3_share"]) <= 0.6:
        verdict = CONCENTRATION_BROAD
    else:
        verdict = CONCENTRATION_SELECTIVE
    result["verdict"] = verdict
    return result
