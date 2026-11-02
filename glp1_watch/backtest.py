"""Phase 5: backtesting — two tracks, honesty-first.

Track A (runnable now): price-rule strategies on the cached ~400-day
price history. Labeled exploratory and subject to current-universe
survivorship bias: the ticker roster is today's, so delisted or
acquired names are absent. Do not overinterpret annualized results
from roughly 400 days.

Track B (walk-forward only): decision-rule strategies (tier-based,
catalyst-confirmed, persistence-confirmed re-entry, avoid-new-capital)
require recorded live decisions. No reconstructed historical tiers,
catalysts, or recommendations — ever. Track B reports its status and
waits for live journal history to accumulate.

Every Track A result carries: tested period, observation count,
rebalance frequency, transaction-cost assumption, and the list of
unavailable metrics/strategies.
"""

from __future__ import annotations

import pandas as pd

from .decision_journal import _extract_closes

TRACK_A_LABEL = (
    "EXPLORATORY — current-universe survivorship bias; "
    "~400 days of history; do not overinterpret annualized figures."
)

TRANSACTION_COST = 0.001  # 10 bps per rebalance, documented assumption
REBALANCE_FREQ = "monthly (21 trading days)"

ANNUALIZATION_MIN_DAYS = 730  # below this, annualized figures are flagged

UNAVAILABLE_TRACK_A = [
    "tier-based decision framework (Track B — needs live decisions)",
    "catalyst-confirmed strategy (Track B)",
    "persistence-confirmed re-entry (Track B)",
    "avoid-new-capital rules (Track B)",
]


def _daily_returns(closes: pd.DataFrame) -> pd.DataFrame:
    return closes.pct_change().dropna(how="all")


def _rebalance_dates(index: pd.DatetimeIndex, freq_days: int = 21) -> pd.DatetimeIndex:
    return index[::freq_days]


def _simulate_equal_weight_portfolio(
    returns: pd.DataFrame,
    rebalance_idx: pd.DatetimeIndex,
    transaction_cost: float,
) -> tuple[pd.Series, pd.Series]:
    """Return net daily returns and turnover for a periodic equal-weight strategy.

    Weights are set to equal weight at inception and on scheduled rebalance
    dates, then drift with asset returns between rebalances.  This is materially
    different from multiplying every day's returns by a constant equal-weight
    vector, which is a daily-rebalanced strategy and understates turnover.
    """
    members = list(returns.columns)
    weights = pd.Series(0.0, index=members, dtype=float)
    rebalance_dates = set(rebalance_idx)
    net_returns: list[float] = []
    turnovers: list[float] = []

    for position, (as_of_date, row) in enumerate(returns.iterrows()):
        turnover = 0.0
        if position == 0 or as_of_date in rebalance_dates:
            # Do not allocate to a member before it has a usable return.  Once
            # held, a missing daily return is conservatively treated as flat.
            eligible = row.index[row.notna()].tolist()
            target = pd.Series(0.0, index=members, dtype=float)
            if eligible:
                target.loc[eligible] = 1.0 / len(eligible)
            turnover = 1.0 if position == 0 and eligible else float(
                (target - weights).abs().sum() / 2.0
            )
            weights = target

        asset_returns = pd.to_numeric(row, errors="coerce").fillna(0.0)
        gross_return = float((weights * asset_returns).sum())
        net_returns.append(gross_return - turnover * transaction_cost)
        turnovers.append(turnover)

        # End-of-day holdings become the next day's starting weights.  A
        # proportional transaction cost changes equity, not relative weights.
        ending_values = weights * (1.0 + asset_returns)
        ending_total = float(ending_values.sum())
        if ending_total > 0:
            weights = ending_values / ending_total

    return (
        pd.Series(net_returns, index=returns.index, dtype=float),
        pd.Series(turnovers, index=returns.index, dtype=float),
    )


def run_track_a(
    price_history: pd.DataFrame,
    strategies: dict[str, list[str]],
    benchmarks: list[str] | None = None,
    transaction_cost: float = TRANSACTION_COST,
) -> dict:
    """Run Track A price-rule backtests. Pure function, no writes."""
    closes = _extract_closes(price_history)
    if closes.empty:
        return {"status": "no data", "results": {}}
    returns = _daily_returns(closes)
    if returns.empty:
        return {"status": "no data", "results": {}}

    benchmarks = benchmarks or ["SPY", "QQQ", "XLV", "XBI"]
    start, end = returns.index[0], returns.index[-1]
    n_days = len(returns)
    rebalance_idx = _rebalance_dates(returns.index)
    n_rebalances = len(rebalance_idx)

    results: dict[str, dict] = {}
    for name, tickers in strategies.items():
        members = [t for t in tickers if t in returns.columns]
        if not members:
            results[name] = {"status": "no members in price history"}
            continue
        # Equal weights are known without observing the current day's return,
        # so scheduled rebalances occur at the start of the rebalance date.
        # Holdings then drift until the next scheduled rebalance.
        net, turnover_events = _simulate_equal_weight_portfolio(
            returns[members], rebalance_idx, transaction_cost
        )
        equity = (1.0 + net).cumprod()
        total_return = float(equity.iloc[-1] - 1.0)
        years = n_days / 252.0
        annualized = float((1.0 + total_return) ** (1.0 / years) - 1.0) if years > 0 else 0.0
        volatility = float(net.std() * (252.0 ** 0.5)) if len(net) > 1 else 0.0
        running_max = equity.cummax()
        max_drawdown = float(((equity - running_max) / running_max).min())
        monthly = net.resample("ME").apply(lambda s: (1.0 + s).prod() - 1.0)
        win_rate = float((monthly > 0).mean()) if len(monthly) else 0.0
        turnover = float(turnover_events.sum())
        bench_excess = {}
        for bench in benchmarks:
            if bench in returns.columns:
                bench_tr = float((1.0 + returns[bench].fillna(0.0)).prod() - 1.0)
                bench_excess[bench] = total_return - bench_tr
        results[name] = {
            "status": "ok",
            "total_return": round(total_return, 4),
            "annualized_return": round(annualized, 4),
            "annualized_reliable": n_days >= ANNUALIZATION_MIN_DAYS,
            "volatility_ann": round(volatility, 4),
            "max_drawdown": round(max_drawdown, 4),
            "turnover": round(turnover, 2),
            "n_rebalances": n_rebalances,
            "monthly_win_rate": round(win_rate, 3),
            "excess_return_vs_benchmarks": {k: round(v, 4) for k, v in bench_excess.items()},
            "n_members": len(members),
        }

    return {
        "status": "ok",
        "label": TRACK_A_LABEL,
        "period": {"start": start.strftime("%Y-%m-%d"), "end": end.strftime("%Y-%m-%d")},
        "n_days": n_days,
        "n_months": int(n_days / 21),
        "rebalance_frequency": REBALANCE_FREQ,
        "transaction_cost_assumption": transaction_cost,
        "unavailable": UNAVAILABLE_TRACK_A,
        "results": results,
    }


def track_a_strategies(sleeves: list) -> dict[str, list[str]]:
    """The three honest price-rule strategies from the sleeve roster."""
    required = [s for s in sleeves if s.required]
    all_required = [t for s in required for t in s.tickers]
    leaders = []
    for s in sleeves:
        if s.name == "Established GLP-1 Leaders":
            leaders = list(s.tickers)
    all_incl_supporting = [t for s in sleeves for t in s.tickers]
    return {
        "equal_weight_stack": all_required,
        "leader_only": leaders,
        "with_supporting_sleeve": all_incl_supporting,
    }


def track_b_status(journal: pd.DataFrame) -> dict:
    """Walk-forward status for decision-rule strategies."""
    if journal is None or getattr(journal, "empty", True):
        return {
            "status": "awaiting first live decision",
            "first_decision": None,
            "days_elapsed": 0,
            "note": (
                "Tier-based, catalyst-confirmed, persistence-confirmed "
                "re-entry, and avoid-new-capital strategies require recorded "
                "live decisions. No historical reconstruction."
            ),
        }
    dates = pd.to_datetime(journal["decision_date"], errors="coerce").dropna()
    if dates.empty:
        return {"status": "awaiting first live decision", "first_decision": None,
                "days_elapsed": 0, "note": "No dated decisions yet."}
    first = dates.min()
    days = (pd.Timestamp.now().normalize() - first.normalize()).days
    return {
        "status": "walk-forward",
        "first_decision": first.strftime("%Y-%m-%d"),
        "days_elapsed": int(days),
        "n_decisions": int(len(journal)),
        "note": (
            "Decision-rule strategies run walk-forward from the first "
            "recorded live decision. No reconstructed historical tiers, "
            "catalysts, or recommendations."
        ),
    }


def summarize_track_a(backtest: dict) -> list[str]:
    """Report lines for Track A results."""
    lines = []
    if backtest.get("status") != "ok":
        return ["- Track A backtest: no usable price history."]
    lines.append(f"- {backtest['label']}")
    period = backtest["period"]
    lines.append(
        f"- Tested period: {period['start']} to {period['end']} "
        f"({backtest['n_days']} trading days, ~{backtest['n_months']} months)."
    )
    lines.append(f"- Rebalance: {backtest['rebalance_frequency']}; "
                 f"cost assumption: {backtest['transaction_cost_assumption']:.1%} per rebalance.")
    for name, res in backtest["results"].items():
        if res.get("status") != "ok":
            lines.append(f"- {name}: {res.get('status')}.")
            continue
        ann = f"{res['annualized_return']:.1%}"
        if not res["annualized_reliable"]:
            ann += " (unreliable — under 2 years of history)"
        lines.append(
            f"- {name} ({res['n_members']} names): total {res['total_return']:.1%}, "
            f"annualized {ann}, vol {res['volatility_ann']:.1%}, "
            f"max DD {res['max_drawdown']:.1%}, turnover {res['turnover']:.1f}, "
            f"monthly win rate {res['monthly_win_rate']:.0%}."
        )
        for bench, excess in res["excess_return_vs_benchmarks"].items():
            lines.append(f"  - Excess vs {bench}: {excess:+.1%}.")
    lines.append(f"- Unavailable in Track A: {'; '.join(backtest['unavailable'])}.")
    return lines
