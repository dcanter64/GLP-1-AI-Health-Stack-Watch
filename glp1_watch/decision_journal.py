"""Phase 5: decision journal with forward-outcome accountability.

One row per (decision_date, entity_type, entity_name). Decision-time
fields are immutable after insertion: later runs may fill only outcome
fields and their measurement dates. Forward returns are never
fabricated — they are filled only when the maturity date has arrived,
using the first available trading close on or after maturity (never
interpolated, never before maturity). Once recorded, outcomes are
immutable unless an explicit repair operation is invoked.

Entity types: "sleeve" and "ticker".
Unique key: (decision_date, entity_type, entity_name).
"""

from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

JOURNAL_FILENAME = "decision_journal.csv"

ENTITY_SLEEVE = "sleeve"
ENTITY_TICKER = "ticker"

DECISION_FIELDS = [
    "decision_date",
    "entity_type",
    "entity_name",
    "methodology_version",
    "decision_price",
    "decision_price_date",
    "recommendation",
    "recommended_tier",
    "confidence",
    "urgency",
    "evidence",
    "upgrade_condition",
    "downgrade_condition",
    "invalidation_condition",
]

OUTCOME_FIELDS = [
    "outcome_1m",
    "outcome_1m_date",
    "outcome_3m",
    "outcome_3m_date",
    "outcome_6m",
    "outcome_6m_date",
]

JOURNAL_COLUMNS = DECISION_FIELDS + OUTCOME_FIELDS

HORIZON_DAYS = {"1m": 30, "3m": 91, "6m": 182}


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _normalize_key(entity_type: object, entity_name: object) -> tuple[str, str]:
    """Journal-boundary normalization (M7b).

    entity_type is lowercased/stripped and must be "sleeve" or "ticker".
    Ticker names are uppercased/stripped; sleeve names keep their canonical
    casing (stripped). Cheapest to enforce before history accumulates.
    """
    etype = "" if _is_missing(entity_type) else str(entity_type).strip().lower()
    if etype not in (ENTITY_SLEEVE, ENTITY_TICKER):
        raise ValueError(
            f"decision_journal: invalid entity_type {entity_type!r}; "
            f"must be {ENTITY_SLEEVE!r} or {ENTITY_TICKER!r}"
        )
    if _is_missing(entity_name):
        raise ValueError("decision_journal: entity_name must not be blank")
    name = str(entity_name).strip()
    if etype == ENTITY_TICKER:
        name = name.upper()
    if not name:
        raise ValueError("decision_journal: entity_name must not be blank")
    return etype, name


def _journal_path(history_dir: str | Path) -> Path:
    return Path(history_dir) / JOURNAL_FILENAME


def load_journal(history_dir: str | Path) -> pd.DataFrame:
    """Read the journal; empty frame when absent or corrupt."""
    path = _journal_path(history_dir)
    if not path.exists():
        return pd.DataFrame(columns=JOURNAL_COLUMNS)
    try:
        frame = pd.read_csv(path)
    except Exception:
        return pd.DataFrame(columns=JOURNAL_COLUMNS)
    for column in JOURNAL_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame["decision_date"] = pd.to_datetime(
        frame["decision_date"], format="%Y-%m-%d", errors="coerce"
    )
    frame = frame.dropna(subset=["decision_date", "entity_type", "entity_name"])
    return frame.sort_values(
        ["decision_date", "entity_type", "entity_name"]
    ).reset_index(drop=True)


def _write_journal(history_dir: str | Path, frame: pd.DataFrame) -> pd.DataFrame:
    """Atomic write of the journal frame."""
    path = _journal_path(history_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = frame.copy()
    if not out.empty:
        # Normalize keys at the write boundary, then reject duplicates
        # loudly (M7a/M7b): silent keep="last"/"first" could overwrite
        # immutable decision fields.
        for col in ("entity_type", "entity_name"):
            if col not in out.columns:
                out[col] = ""
        normalized = [
            _normalize_key(et, en)
            for et, en in zip(out["entity_type"], out["entity_name"])
        ]
        out["entity_type"] = [et for et, _ in normalized]
        out["entity_name"] = [en for _, en in normalized]
        out["decision_date"] = pd.to_datetime(
            out["decision_date"], format="%Y-%m-%d", errors="coerce"
        )
        out = out.dropna(subset=["decision_date", "entity_type", "entity_name"])
        dupes = out.duplicated(
            subset=["decision_date", "entity_type", "entity_name"], keep=False
        )
        if dupes.any():
            bad = (
                out.loc[dupes, ["decision_date", "entity_type", "entity_name"]]
                .drop_duplicates()
                .to_dict("records")
            )
            raise ValueError(
                "decision_journal: duplicate keys rejected — decision-time "
                f"fields are immutable and must not be overwritten: {bad}"
            )
        out = out.sort_values(["decision_date", "entity_type", "entity_name"]).reset_index(
            drop=True
        )
        out["decision_date"] = out["decision_date"].dt.strftime("%Y-%m-%d")
    out = out.reindex(columns=JOURNAL_COLUMNS)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            out.to_csv(handle, index=False)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return load_journal(history_dir)


def append_journal_entries(
    history_dir: str | Path,
    entries: list[dict],
    as_of_dt,
) -> pd.DataFrame:
    """Insert new decisions. Decision-time fields of existing rows are
    never overwritten — only outcome fields may be filled later.

    Only call when outputs are being written (dry-run purity).
    """
    date_str = as_of_dt.strftime("%Y-%m-%d")
    today = pd.Timestamp(date.today().isoformat())
    if pd.Timestamp(date_str) > today:
        raise ValueError(
            f"decision_journal: refusing to record future decision date: {date_str}"
        )
    existing = load_journal(history_dir)
    existing_keys = set(
        zip(
            existing["decision_date"].dt.strftime("%Y-%m-%d"),
            existing["entity_type"].astype(str),
            existing["entity_name"].astype(str),
        )
    ) if not existing.empty else set()

    new_rows = []
    for entry in entries:
        etype, ename = _normalize_key(entry.get("entity_type"), entry.get("entity_name"))
        key = (date_str, etype, ename)
        if key in existing_keys:
            continue  # immutable: never re-insert decision-time fields
        row = {col: entry.get(col) for col in JOURNAL_COLUMNS}
        row["decision_date"] = date_str
        row["entity_type"] = etype
        row["entity_name"] = ename
        new_rows.append(row)

    if not new_rows:
        return existing
    new_frame = pd.DataFrame(new_rows, columns=JOURNAL_COLUMNS)
    combined = pd.concat([existing, new_frame], ignore_index=True)
    return _write_journal(history_dir, combined)


def _first_close_on_or_after(
    closes: pd.Series, maturity: pd.Timestamp
) -> tuple[float | None, pd.Timestamp | None]:
    """First available trading close on or after maturity. No interpolation."""
    eligible = closes[closes.index >= maturity]
    if eligible.empty:
        return None, None
    price = eligible.iloc[0]
    if pd.isna(price):
        return None, None
    return float(price), eligible.index[0]


def _last_close_on_or_before(
    closes: pd.Series, as_of: pd.Timestamp
) -> tuple[float | None, pd.Timestamp | None]:
    """Last available trading close on or before the decision date.

    Used for decision prices: a Sunday report prices off Friday's close,
    never a future close.
    """
    eligible = closes[closes.index <= as_of]
    if eligible.empty:
        return None, None
    price = eligible.iloc[-1]
    if pd.isna(price):
        return None, None
    return float(price), eligible.index[-1]


def fill_forward_outcomes(
    journal: pd.DataFrame,
    price_history: pd.DataFrame,
    sleeve_members: dict[str, list[str]] | None = None,
) -> pd.DataFrame:
    """Fill matured but unfilled outcome fields. Pure function — the caller
    decides whether to persist the result (dry runs must not write).

    - Ticker outcomes: forward return vs the decision price.
    - Sleeve outcomes: equal-weight member forward return (decision_price
      is NULL for sleeves; outcomes are returns, not prices).
    - Outcomes already recorded are never changed here.
    """
    if journal.empty:
        return journal.copy()
    closes = _extract_closes(price_history)
    if closes.empty:
        return journal.copy()
    latest = closes.index.max()

    out = journal.copy()
    for idx, row in out.iterrows():
        decision_date = pd.to_datetime(row["decision_date"])
        for horizon, days in HORIZON_DAYS.items():
            ret_col = f"outcome_{horizon}"
            date_col = f"outcome_{horizon}_date"
            if not pd.isna(row.get(ret_col)):
                continue  # immutable once recorded
            maturity = decision_date + timedelta(days=days)
            if maturity > latest:
                continue  # not matured — never fill early
            entity_type = str(row["entity_type"])
            if entity_type == ENTITY_TICKER:
                ticker = str(row["entity_name"])
                if ticker not in closes.columns:
                    continue
                base_price = _safe_float(row.get("decision_price"))
                base_date = pd.to_datetime(row.get("decision_price_date"), errors="coerce")
                if base_price is None or pd.isna(base_date):
                    continue
                price, price_date = _first_close_on_or_after(closes[ticker], maturity)
                if price is None:
                    continue
                out.at[idx, ret_col] = price / base_price - 1.0
                out.at[idx, date_col] = price_date.strftime("%Y-%m-%d")
            elif entity_type == ENTITY_SLEEVE:
                members = (sleeve_members or {}).get(str(row["entity_name"]), [])
                member_closes = [c for c in members if c in closes.columns]
                if not member_closes:
                    continue
                fwd_returns = []
                price_dates = []
                for ticker in member_closes:
                    # M5: same decision-date convention as tickers — last
                    # close on or before the decision date for the base.
                    base, _ = _last_close_on_or_before(closes[ticker], decision_date)
                    price, price_date = _first_close_on_or_after(closes[ticker], maturity)
                    if base and price:
                        fwd_returns.append(price / base - 1.0)
                        price_dates.append(price_date)
                if not fwd_returns:
                    continue
                out.at[idx, ret_col] = sum(fwd_returns) / len(fwd_returns)
                # M4: record the actual trading date used (the latest member
                # price date), never a synthetic Sunday maturity date.
                out.at[idx, date_col] = max(price_dates).strftime("%Y-%m-%d")
    return out


def repair_outcomes(
    history_dir: str | Path,
    journal: pd.DataFrame,
    price_history: pd.DataFrame,
    sleeve_members: dict[str, list[str]] | None = None,
) -> pd.DataFrame:
    """Explicit repair: recompute ALL outcomes from scratch, including
    already-recorded ones. Loud, deliberate, never called by the pipeline.
    Returns the repaired frame and persists it.
    """
    cleared = journal.copy()
    for horizon in HORIZON_DAYS:
        cleared[f"outcome_{horizon}"] = pd.NA
        cleared[f"outcome_{horizon}_date"] = pd.NA
    repaired = fill_forward_outcomes(cleared, price_history, sleeve_members)
    return _write_journal(history_dir, repaired)


def _extract_closes(price_history: pd.DataFrame) -> pd.DataFrame:
    """Close-price matrix from the cached market snapshot.

    Handles both MultiIndex layouts (Close x ticker and ticker x Close)
    and plain single-level frames.
    """
    if price_history is None or getattr(price_history, "empty", True):
        return pd.DataFrame()
    frame = price_history.copy()
    # MultiIndex columns -> keep the Close level, whichever position it is in.
    if isinstance(frame.columns, pd.MultiIndex):
        closes = None
        for level in range(frame.columns.nlevels):
            try:
                candidate = frame.xs("Close", axis=1, level=level)
            except KeyError:
                continue
            closes = candidate
            break
        if closes is None:
            return pd.DataFrame()
    else:
        closes = frame
    closes.index = pd.to_datetime(closes.index)
    # M2: normalize tz-aware indexes to tz-naive at the fill boundary.
    # A tz-aware price index must never crash the unconditional journal-fill
    # path with a tz-naive/tz-aware comparison TypeError.
    try:
        if closes.index.tz is not None:
            closes.index = closes.index.tz_localize(None)
    except AttributeError:
        pass
    return closes.sort_index()


def _safe_float(value: object) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_journal_entries(
    *,
    decision_cards: list[dict],
    position_cards: list[dict],
    price_history: pd.DataFrame,
    methodology_version: str,
    as_of_dt,
) -> list[dict]:
    """Decision-time journal entries for sleeves and tickers."""
    closes = _extract_closes(price_history)
    entries = []
    for card in decision_cards:
        entries.append(
            {
                "entity_type": ENTITY_SLEEVE,
                "entity_name": card["sleeve"],
                "methodology_version": methodology_version,
                "decision_price": None,  # sleeves: outcomes are eq-wt returns
                "decision_price_date": None,
                "recommendation": card["recommendation"],
                "recommended_tier": card["recommended_tier"],
                "confidence": card["confidence"],
                "urgency": card["urgency"],
                "evidence": card.get("rationale", ""),
                "upgrade_condition": card.get("upgrade_condition", ""),
                "downgrade_condition": card.get("downgrade_condition", ""),
                "invalidation_condition": card.get("invalidation_condition", ""),
            }
        )
    for card in position_cards:
        ticker = card["ticker"]
        price, price_date = (None, None)
        if not closes.empty and ticker in closes.columns:
            price, price_date = _last_close_on_or_before(
                closes[ticker], pd.Timestamp(as_of_dt.strftime("%Y-%m-%d"))
            )
        entries.append(
            {
                "entity_type": ENTITY_TICKER,
                "entity_name": ticker,
                "methodology_version": methodology_version,
                "decision_price": price,
                "decision_price_date": (
                    price_date.strftime("%Y-%m-%d") if price_date is not None else None
                ),
                "recommendation": card["recommendation"],
                "recommended_tier": card["tier"],
                "confidence": card["confidence"],
                "urgency": card["urgency"],
                "evidence": card.get("reason", ""),
                "upgrade_condition": card.get("upgrade_condition", ""),
                "downgrade_condition": card.get("downgrade_condition", ""),
                "invalidation_condition": card.get("invalidation_condition", ""),
            }
        )
    return entries


def persist_filled_journal(history_dir: str | Path, journal: pd.DataFrame) -> pd.DataFrame:
    """Write a filled journal frame back to disk (real runs only)."""
    return _write_journal(history_dir, journal)
