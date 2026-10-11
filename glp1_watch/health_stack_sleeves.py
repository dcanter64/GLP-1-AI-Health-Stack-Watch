"""Phase 1: health-stack sleeve configuration loading and validation.

Sleeves are defined in ``config/health_stack_sleeves.yaml``. Ticker membership
is operator-editable there; the analytical structure is validated loudly here:

- every ticker must exist in the market-data universe (``TICKER_GROUPS``)
- no ticker may appear in more than one sleeve
- XLV, QQQ, and SPY are comparators and may not be sleeve members
- the set of required sleeves must match the expected seven

Any violation raises ``ValueError`` instead of silently degrading the output.

Outage mode (by design): ``load_sleeve_config()`` is a hard dependency of
``build_dashboard_snapshot``. A missing or invalid YAML file raises out of the
pipeline and fails the whole run — there is no graceful fallback, because a
silently wrong sleeve map would be worse than a loud failure. Validate the
YAML (``python -m pytest tests/test_health_stack_sleeves.py``) after editing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .config import TICKER_GROUPS

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "health_stack_sleeves.yaml"

#: Tickers reserved as comparators; never sleeve members.
COMPARATOR_TICKERS = ("XLV", "QQQ", "SPY")

#: Structural expectation for Phase 1: exactly these sleeves are required.
#: Core health-stack breadth counts are calculated from these seven only.
EXPECTED_REQUIRED_SLEEVES = frozenset(
    {
        "Established GLP-1 Leaders",
        "Emerging GLP-1 Challengers",
        "Large-Pharma GLP-1 Optionality",
        "AI Drug-Discovery Platforms",
        "Gene Editing and Precision Medicine",
        "Health Data and Clinical AI",
        "Broad Biotech Risk Appetite",
    }
)


@dataclass(frozen=True)
class Sleeve:
    """One analytical sleeve: a named, non-overlapping ticker set."""

    name: str
    tickers: tuple[str, ...]
    required: bool
    description: str = ""


def market_universe_tickers() -> list[str]:
    """All tickers the market-data layer can provide (from TICKER_GROUPS)."""
    tickers: list[str] = []
    for group_tickers in TICKER_GROUPS.values():
        for ticker in group_tickers:
            if ticker not in tickers:
                tickers.append(ticker)
    return tickers


def load_sleeve_config(path: str | Path = CONFIG_PATH) -> list[Sleeve]:
    """Load and validate the sleeve configuration.

    Raises:
        FileNotFoundError: if the YAML file does not exist.
        ValueError: if the structure, membership, or required set is invalid.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Sleeve config not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict) or not isinstance(data.get("sleeves"), list):
        raise ValueError("Sleeve config must be a mapping with a 'sleeves' list.")

    universe = set(market_universe_tickers())
    sleeves: list[Sleeve] = []
    seen_names: set[str] = set()
    ticker_owner: dict[str, str] = {}

    for index, entry in enumerate(data["sleeves"]):
        if not isinstance(entry, dict):
            raise ValueError(f"Sleeve entry #{index} must be a mapping.")
        name = entry.get("name")
        raw_tickers = entry.get("tickers")
        required = entry.get("required")
        description = entry.get("description", "")

        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Sleeve entry #{index} is missing a valid 'name'.")
        name = name.strip()
        if name in seen_names:
            raise ValueError(f"Duplicate sleeve name: {name!r}.")
        seen_names.add(name)

        if not isinstance(raw_tickers, list) or not raw_tickers:
            raise ValueError(f"Sleeve {name!r} must define a non-empty 'tickers' list.")
        if not isinstance(required, bool):
            raise ValueError(f"Sleeve {name!r} must define 'required' as true or false.")

        tickers: list[str] = []
        for raw_ticker in raw_tickers:
            if not isinstance(raw_ticker, str):
                raise ValueError(f"Sleeve {name!r} has a non-string ticker entry: {raw_ticker!r}.")
            ticker = raw_ticker.strip().upper()
            if not ticker:
                raise ValueError(f"Sleeve {name!r} has a blank ticker entry.")
            if ticker in COMPARATOR_TICKERS:
                raise ValueError(
                    f"Sleeve {name!r}: {ticker} is a comparator and cannot be a sleeve member."
                )
            if ticker not in universe:
                raise ValueError(
                    f"Sleeve {name!r}: unknown ticker {ticker!r} (not in market-data universe)."
                )
            if ticker in ticker_owner:
                owner = ticker_owner[ticker]
                if owner == name:
                    raise ValueError(
                        f"Duplicate ticker membership: {ticker} appears twice in {name!r}."
                    )
                raise ValueError(
                    f"Duplicate ticker membership: {ticker} appears in both "
                    f"{owner!r} and {name!r}."
                )
            ticker_owner[ticker] = name
            tickers.append(ticker)

        sleeves.append(
            Sleeve(
                name=name,
                tickers=tuple(tickers),
                required=required,
                description=str(description or "").strip(),
            )
        )

    required_names = frozenset(sleeve.name for sleeve in sleeves if sleeve.required)
    if required_names != EXPECTED_REQUIRED_SLEEVES:
        raise ValueError(
            "Required sleeve set mismatch: expected "
            f"{sorted(EXPECTED_REQUIRED_SLEEVES)}, got {sorted(required_names)}."
        )
    return sleeves


def ticker_to_sleeve_map(sleeves: list[Sleeve]) -> dict[str, str]:
    """Map each ticker to its sleeve name."""
    return {ticker: sleeve.name for sleeve in sleeves for ticker in sleeve.tickers}


def required_sleeves(sleeves: list[Sleeve]) -> list[Sleeve]:
    """The seven required sleeves that define core health-stack breadth."""
    return [sleeve for sleeve in sleeves if sleeve.required]


def core_breadth_tickers(sleeves: list[Sleeve]) -> list[str]:
    """Tickers in required sleeves only (excludes supporting sleeves)."""
    return [ticker for sleeve in required_sleeves(sleeves) for ticker in sleeve.tickers]
