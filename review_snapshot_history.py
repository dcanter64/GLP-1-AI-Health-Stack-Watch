from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
HISTORY_PATH = BASE_DIR / "output" / "history" / "dashboard_scores.jsonl"
VALIDATION_DIR = BASE_DIR / "output" / "validation"


def load_score_history() -> pd.DataFrame:
    if not HISTORY_PATH.exists():
        return pd.DataFrame(
            columns=[
                "as_of_date",
                "overall_score",
                "stance",
                "lly_ai_trade_score",
                "article_count",
                "accepted_story_count",
                "qualified_story_count",
            ]
        )

    rows = []
    for line in HISTORY_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))

    history = pd.DataFrame(rows)
    if history.empty:
        return history
    history["as_of_date"] = pd.to_datetime(history["as_of_date"], utc=True, errors="coerce")
    if "accepted_story_count" not in history.columns:
        history["accepted_story_count"] = history["article_count"]
    else:
        history["accepted_story_count"] = history["accepted_story_count"].fillna(history["article_count"])
    if "qualified_story_count" not in history.columns:
        history["qualified_story_count"] = pd.NA
    return history.sort_values("as_of_date").reset_index(drop=True)


def latest_validation_metrics() -> dict[str, str]:
    validation_files = sorted(VALIDATION_DIR.glob("validation_*.md"))
    if not validation_files:
        return {}

    latest = validation_files[-1]
    metrics: dict[str, str] = {"file": latest.name}
    for line in latest.read_text(encoding="utf-8").splitlines():
        if not line.startswith("- "):
            continue
        if ":" not in line:
            continue
        label, value = line[2:].split(":", 1)
        metrics[label.strip()] = value.strip()
    return metrics


def summarize_history(history: pd.DataFrame) -> list[str]:
    if history.empty:
        return ["No score history is available yet."]

    latest = history.iloc[-1]
    summary = [
        f"Snapshots tracked: {len(history)}",
        f"Latest snapshot: {latest['as_of_date'].strftime('%Y-%m-%d %H:%M UTC')}",
        f"Latest score: {latest['overall_score']:.1f} ({latest['stance']})",
        f"Latest LLY AI trade score: {latest['lly_ai_trade_score']:.1f}",
        f"Latest accepted-story count: {int(latest['accepted_story_count'])}",
        (
            f"Latest qualified-story count: {int(latest['qualified_story_count'])}"
            if pd.notna(latest["qualified_story_count"])
            else "Latest qualified-story count: unavailable in older history entries"
        ),
        f"Average overall score: {history['overall_score'].mean():.1f}",
        f"Average accepted-story count: {history['accepted_story_count'].mean():.1f}",
    ]

    qualified_series = history["qualified_story_count"].dropna()
    if not qualified_series.empty:
        summary.append(f"Average qualified-story count: {qualified_series.mean():.1f}")

    if len(history) >= 2:
        prior = history.iloc[-2]
        summary.append(
            f"Change vs prior snapshot: score {latest['overall_score'] - prior['overall_score']:+.1f}, "
            f"accepted stories {int(latest['accepted_story_count'] - prior['accepted_story_count']):+d}"
        )
        if pd.notna(latest["qualified_story_count"]) and pd.notna(prior["qualified_story_count"]):
            summary.append(
                f"Change vs prior snapshot: qualified stories "
                f"{int(latest['qualified_story_count'] - prior['qualified_story_count']):+d}"
            )

    return summary


def summarize_validation(metrics: dict[str, str]) -> list[str]:
    if not metrics:
        return ["No validation audit files are available yet."]

    labels = [
        "file",
        "Ticker rows",
        "Total stories fetched",
        "Stories rejected by relevance gate",
        "Stories rejected by exclusion filter",
        "Accepted stories",
        "Qualified scoring stories",
        "Scoring coverage",
        "News confidence",
        "Market data error",
        "Ticker exceptions applied",
    ]
    return [f"{label}: {metrics[label]}" for label in labels if label in metrics]


def main() -> None:
    history = load_score_history()
    validation = latest_validation_metrics()

    print("GLP-1 AI Health Stack Watch Calibration Review")
    print("")
    print("Score History")
    for line in summarize_history(history):
        print(f"- {line}")

    print("")
    print("Latest Validation Audit")
    for line in summarize_validation(validation):
        print(f"- {line}")


if __name__ == "__main__":
    main()
