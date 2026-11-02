from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

from .cache import load_cached_dataframe, save_cached_dataframe
from .config import BENCHMARKS, CACHE_DIR, LOOKBACK_DAYS, RS_COMPARATORS, TICKER_EXCEPTIONS, TICKER_GROUPS


@dataclass
class MarketSnapshot:
    price_history: pd.DataFrame
    performance_table: pd.DataFrame
    layer_performance: pd.DataFrame
    ticker_diagnostics: dict[str, object]


def apply_ticker_exceptions(tickers: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    resolved: list[str] = []
    diagnostics: list[dict[str, str]] = []

    for ticker in tickers:
        exception = TICKER_EXCEPTIONS.get(ticker)
        if not exception:
            if ticker not in resolved:
                resolved.append(ticker)
            continue

        action = str(exception.get("action", "keep")).lower()
        reason = str(exception.get("reason", "")).strip()
        replacement = str(exception.get("replacement", "")).strip().upper()

        if action == "drop":
            diagnostics.append(
                {
                    "ticker": ticker,
                    "action": "drop",
                    "replacement": "",
                    "reason": reason or "Ticker removed by exception rule.",
                }
            )
            continue

        if action == "replace" and replacement:
            diagnostics.append(
                {
                    "ticker": ticker,
                    "action": "replace",
                    "replacement": replacement,
                    "reason": reason or f"Ticker remapped to {replacement}.",
                }
            )
            if replacement not in resolved:
                resolved.append(replacement)
            continue

        if ticker not in resolved:
            resolved.append(ticker)

    return resolved, diagnostics


def get_all_tickers() -> tuple[list[str], list[dict[str, str]]]:
    tickers: list[str] = []
    for group_tickers in TICKER_GROUPS.values():
        for ticker in group_tickers:
            if ticker not in tickers:
                tickers.append(ticker)
    return apply_ticker_exceptions(tickers)


def download_price_history(
    tickers: list[str],
    lookback_days: int = LOOKBACK_DAYS,
    max_age_hours: int = 6,
    force_refresh: bool = False,
) -> pd.DataFrame:
    period_start = (datetime.utcnow() - timedelta(days=lookback_days)).date().isoformat()
    cache_key = f"{','.join(sorted(tickers))}|{period_start}|1d"
    if not force_refresh:
        cached = load_cached_dataframe(CACHE_DIR, "prices", cache_key, max_age_hours=max_age_hours)
        if cached is not None:
            return cached

    _prepare_yfinance_cache(CACHE_DIR / "yfinance")

    df = _download_prices_bulk(tickers, period_start)
    if df.empty:
        df = _download_prices_sequential(tickers, period_start)
    if df.empty:
        raise RuntimeError("yfinance returned no price history.")

    save_cached_dataframe(CACHE_DIR, "prices", cache_key, df, header_rows=2)
    return df


def _prepare_yfinance_cache(cache_path: Path) -> None:
    cache_path.mkdir(parents=True, exist_ok=True)
    try:
        yf.set_tz_cache_location(str(cache_path))
    except Exception:
        pass


def _download_prices_bulk(tickers: list[str], period_start: str) -> pd.DataFrame:
    try:
        return yf.download(
            tickers=tickers,
            start=period_start,
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=False,
            group_by="column",
        )
    except Exception:
        return pd.DataFrame()


def _download_prices_sequential(tickers: list[str], period_start: str) -> pd.DataFrame:
    closes: list[pd.DataFrame] = []
    for ticker in tickers:
        try:
            history = yf.Ticker(ticker).history(start=period_start, interval="1d", auto_adjust=True)
            if history.empty or "Close" not in history.columns:
                continue
            closes.append(history[["Close"]].rename(columns={"Close": ticker}))
        except Exception:
            continue

    if not closes:
        return pd.DataFrame()

    close_df = pd.concat(closes, axis=1).sort_index()
    multi_columns = pd.MultiIndex.from_product([["Close"], close_df.columns])
    close_df.columns = multi_columns
    return close_df


def extract_close_prices(price_history: pd.DataFrame) -> pd.DataFrame:
    if isinstance(price_history.columns, pd.MultiIndex):
        close = price_history["Close"].copy()
    else:
        close = price_history.rename(columns={"Close": "Unknown"})[["Unknown"]]

    close = close.dropna(axis=1, how="all").sort_index()
    close.index = pd.to_datetime(close.index)
    return close


def compute_returns(close_prices: pd.DataFrame, days: int) -> pd.Series:
    if len(close_prices) <= days:
        return pd.Series(index=close_prices.columns, dtype=float)
    return close_prices.iloc[-1] / close_prices.iloc[-(days + 1)] - 1


def build_performance_table(price_history: pd.DataFrame) -> pd.DataFrame:
    close = extract_close_prices(price_history)
    latest = close.iloc[-1]
    ma50 = close.rolling(50).mean().iloc[-1]
    ma200 = close.rolling(200).mean().iloc[-1]
    high_52w = close.tail(min(252, len(close))).max()
    ytd_start = close[close.index.year == close.index[-1].year].iloc[0]

    perf = pd.DataFrame(index=close.columns)
    perf["price"] = latest
    perf["return_5d"] = compute_returns(close, 5)
    perf["return_1m"] = compute_returns(close, 21)
    perf["return_3m"] = compute_returns(close, 63)
    perf["return_6m"] = compute_returns(close, 126)
    perf["return_ytd"] = latest / ytd_start - 1
    perf["above_50dma"] = latest > ma50
    perf["above_200dma"] = latest > ma200
    perf["distance_from_52w_high"] = latest / high_52w - 1

    for benchmark in RS_COMPARATORS:
        if benchmark not in perf.index or pd.isna(perf.at[benchmark, "return_3m"]):
            perf[f"rs_vs_{benchmark.lower()}"] = pd.NA
            continue
        perf[f"rs_vs_{benchmark.lower()}"] = (
            perf["return_3m"] - float(perf.at[benchmark, "return_3m"])
        )

    ticker_to_group = {
        ticker: group
        for group, group_tickers in TICKER_GROUPS.items()
        for ticker in group_tickers
    }
    perf["group"] = perf.index.map(ticker_to_group)
    perf["is_benchmark"] = perf.index.isin(BENCHMARKS)
    perf = perf.reset_index(names="ticker")
    return perf


def build_layer_performance(performance_table: pd.DataFrame) -> pd.DataFrame:
    windows = ["return_5d", "return_1m", "return_3m", "return_6m"]
    layer_perf = (
        performance_table.groupby("group")[windows]
        .mean(numeric_only=True)
        .sort_values("return_3m", ascending=False)
        .reset_index()
    )
    return layer_perf


def load_market_snapshot(
    lookback_days: int = LOOKBACK_DAYS,
    max_age_hours: int = 6,
    force_refresh: bool = False,
) -> MarketSnapshot:
    tickers, ticker_exception_diagnostics = get_all_tickers()
    price_history = download_price_history(
        tickers,
        lookback_days=lookback_days,
        max_age_hours=max_age_hours,
        force_refresh=force_refresh,
    )
    performance_table = build_performance_table(price_history)
    layer_performance = build_layer_performance(performance_table)
    return MarketSnapshot(
        price_history=price_history,
        performance_table=performance_table,
        layer_performance=layer_performance,
        ticker_diagnostics={
            "requested_count": len(tickers),
            "active_tickers": tickers,
            "exceptions": ticker_exception_diagnostics,
        },
    )
