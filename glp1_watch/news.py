from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse

import feedparser
import pandas as pd
import requests

from .config import (
    EXCLUSION_TERMS,
    NEGATIVE_TERMS,
    NEWS_QUERIES,
    NEWS_TICKERS,
    POSITIVE_TERMS,
    RAW_DIR,
    STRONG_RELEVANCE_TERMS,
    THEME_KEYWORDS,
    THEME_SENTIMENT_BIAS,
    TICKER_ALIASES,
)

MIN_ACCEPTANCE_RELEVANCE_SCORE = 0.45
TICKER_FEED_RELEVANCE_BOOST = 0.16
MAX_NEWS_AGE_DAYS = 21
QUERY_STOPWORDS = {
    "ai",
    "and",
    "cardiovascular",
    "crispr",
    "diabetes",
    "discovery",
    "drug",
    "editing",
    "eli",
    "gene",
    "healthcare",
    "lilly",
    "medicine",
    "obesity",
    "pfizer",
    "therapeutics",
    "trial",
}

LOW_SIGNAL_SEARCH_SOURCES = {
    "24/7 wall st.",
    "argus research",
    "cryptoprowl",
    "freightwaves",
    "motley fool",
    "the street",
    "thestreet",
    "yahoo personal finance",
}

SOURCE_DOMAIN_ALIASES = {
    "247wallst.com": "24/7 Wall St.",
    "advfn.com": "ADVFN",
    "fool.com": "Motley Fool",
    "investors.com": "Investor's Business Daily",
    "marketbeat.com": "MarketBeat",
    "pharmaceutical-technology.com": "Pharmaceutical Technology",
    "proactiveinvestors.com": "Proactive Investors",
    "stocktwits.com": "Stocktwits",
    "thestreet.com": "TheStreet",
    "trefis.com": "Trefis",
    "yahoo.com": "Yahoo Finance",
}


@dataclass
class NewsSnapshot:
    articles: pd.DataFrame
    rejected_articles: pd.DataFrame
    theme_summary: pd.DataFrame
    sentiment_summary: pd.DataFrame
    fetch_errors: list[str]
    raw_payload_path: Path | None
    total_fetched: int
    rejected_by_relevance_gate: int
    rejected_by_exclusion_filter: int
    accepted_story_count: int
    accepted_by_theme: pd.DataFrame
    accepted_by_ticker: pd.DataFrame


def yahoo_rss_urls(query: str) -> list[str]:
    encoded = quote_plus(query)
    return [
        f"https://news.search.yahoo.com/rss?p={encoded}",
        f"https://finance.yahoo.com/rss/search?q={encoded}",
    ]


def yahoo_ticker_rss_url(ticker: str) -> str:
    encoded = quote_plus(ticker)
    return f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={encoded}&region=US&lang=en-US"


def fetch_feed(query: str, timeout: int = 20) -> list[dict[str, Any]]:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; GLP1-AI-Health-Stack-Watch/1.0)"}
    for url in yahoo_rss_urls(query):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            feed = feedparser.parse(response.content)
            if not feed.entries:
                continue
            records = [
                build_raw_article_record(entry, query, url, feed_kind="keyword", target_ticker="")
                for entry in feed.entries
                if entry.get("title") and entry.get("link")
            ]
            return [record for record in records if keyword_candidate_has_evidence(record)]
        except Exception:
            continue
    return []


def fetch_ticker_feed(ticker: str, timeout: int = 20) -> list[dict[str, Any]]:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; GLP1-AI-Health-Stack-Watch/1.0)"}
    url = yahoo_ticker_rss_url(ticker)
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        return [
            build_raw_article_record(entry, f"ticker:{ticker}", url, feed_kind="ticker", target_ticker=ticker)
            for entry in feed.entries
            if entry.get("title") and entry.get("link")
        ]
    except Exception:
        return []


def build_raw_article_record(
    entry: Any,
    query: str,
    feed_url: str,
    feed_kind: str = "keyword",
    target_ticker: str = "",
) -> dict[str, Any]:
    source = ""
    if isinstance(entry.get("source"), dict):
        source = entry.get("source", {}).get("title", "")
    if not source:
        source = derive_source_name(entry.get("link", ""))
    tags = [tag.get("term", "").strip() for tag in entry.get("tags", []) if isinstance(tag, dict)]
    rss_metadata = " | ".join(part for part in [source, *tags] if part)
    return {
        "query": query,
        "feed_url": feed_url,
        "title": entry.get("title", "").strip(),
        "summary": strip_html(entry.get("summary", "")).strip(),
        "url": entry.get("link", "").strip(),
        "source": source,
        "rss_metadata": rss_metadata,
        "feed_kind": feed_kind,
        "target_ticker": target_ticker,
        "published_at": normalize_entry_datetime(entry),
    }


def strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value)


def normalize_entry_datetime(entry: Any) -> str | None:
    for field in ["published", "updated", "pubDate"]:
        value = entry.get(field)
        if not value:
            continue
        try:
            return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
        except Exception:
            continue

    for field in ["published_parsed", "updated_parsed"]:
        parsed = entry.get(field)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()
            except Exception:
                continue

    return None


def article_age_days(article: dict[str, Any]) -> float | None:
    published_at = pd.to_datetime(article.get("published_at"), utc=True, errors="coerce")
    if pd.isna(published_at):
        return None
    return (datetime.now(timezone.utc) - published_at.to_pydatetime()).total_seconds() / 86400.0


def derive_source_name(url: str) -> str:
    try:
        hostname = urlparse(url).hostname or ""
    except Exception:
        return ""

    hostname = hostname.lower().strip()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    if not hostname:
        return ""

    for domain, label in SOURCE_DOMAIN_ALIASES.items():
        if hostname == domain or hostname.endswith(f".{domain}"):
            return label

    parts = [part for part in hostname.split(".") if part and part not in {"com", "net", "org", "co", "io"}]
    if not parts:
        return hostname
    return " ".join(part.capitalize() for part in parts[:2])


def deduplicate_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for article in articles:
        key = article["url"].strip().lower() or article["title"].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(article)
    return deduped


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def term_pattern(term: str) -> str:
    escaped = re.escape(term.lower()).replace(r"\ ", r"\s+")
    if term and term[0].isalnum():
        escaped = rf"(?<!\w){escaped}"
    if term and term[-1].isalnum():
        escaped = rf"{escaped}(?!\w)"
    return escaped


def matched_terms(text: str, terms: list[str]) -> list[str]:
    normalized = normalize_text(text)
    return [term for term in terms if re.search(term_pattern(term), normalized, flags=re.IGNORECASE)]


def classify_theme(text: str) -> str:
    normalized = normalize_text(text)
    scores: dict[str, int] = {}
    for theme, keywords in THEME_KEYWORDS.items():
        scores[theme] = sum(1 for keyword in keywords if re.search(term_pattern(keyword), normalized, flags=re.IGNORECASE))
    best_theme = max(scores, key=scores.get) if scores else "Other"
    return best_theme if scores.get(best_theme, 0) > 0 else "Other"


def score_sentiment(text: str, theme: str) -> tuple[float, str]:
    normalized = normalize_text(text)
    positive_hits = [term for term in POSITIVE_TERMS if re.search(term_pattern(term), normalized, flags=re.IGNORECASE)]
    negative_hits = [term for term in NEGATIVE_TERMS if re.search(term_pattern(term), normalized, flags=re.IGNORECASE)]
    legal_hits = [
        term
        for term in ["sues", "suing", "lawsuit", "legal battle", "injunction", "court order", "in court", "courts"]
        if re.search(term_pattern(term), normalized, flags=re.IGNORECASE)
    ]
    legal_support_hits = [
        term
        for term in ["lly leading", "lilly leading", "lilly leads", "market share gain"]
        if re.search(term_pattern(term), normalized, flags=re.IGNORECASE)
    ]
    score = 0.0
    score += 0.35 * len(positive_hits)
    score -= 0.45 * len(negative_hits)
    score += THEME_SENTIMENT_BIAS.get(theme, 0.0)
    if legal_hits and not legal_support_hits:
        score = min(score, -0.1)
    score = max(-1.0, min(1.0, score))
    explanation = []
    if positive_hits:
        explanation.append(f"positive terms: {', '.join(positive_hits[:3])}")
    if negative_hits:
        explanation.append(f"negative terms: {', '.join(negative_hits[:3])}")
    if legal_hits and not legal_support_hits:
        explanation.append(f"legal dispute terms: {', '.join(legal_hits[:3])}")
    if not explanation:
        explanation.append("keyword-neutral article")
    return score, "; ".join(explanation)


def detect_tickers(text: str) -> list[str]:
    normalized = normalize_text(text)
    matches = []
    for ticker, aliases in TICKER_ALIASES.items():
        ticker_hit = re.search(term_pattern(ticker), normalized, flags=re.IGNORECASE)
        alias_hit = any(re.search(term_pattern(alias), normalized, flags=re.IGNORECASE) for alias in aliases)
        if ticker_hit or alias_hit:
            matches.append(ticker)
    return matches


def relevance_score(theme: str, tickers: list[str], sentiment: float, strong_hits: list[str]) -> float:
    base = 0.45
    base += min(len(strong_hits), 4) * 0.08
    base += min(len(tickers), 3) * 0.12
    if theme in {"GLP-1 Demand", "Lilly AI Infrastructure", "AI Drug Discovery"}:
        base += 0.08
    base += abs(sentiment) * 0.15
    return round(min(base, 1.0), 3)


def article_evidence_text(article: dict[str, Any]) -> str:
    source = article.get("source") or derive_source_name(article.get("url", ""))
    return " ".join(
        part
        for part in [
            article.get("title", ""),
            article.get("summary", ""),
            source,
            article.get("rss_metadata", ""),
        ]
        if part
    )


def article_source(article: dict[str, Any]) -> str:
    return str(article.get("source") or derive_source_name(article.get("url", ""))).strip()


def flatten_relevance_terms() -> list[str]:
    flattened: list[str] = []
    for terms in STRONG_RELEVANCE_TERMS.values():
        for term in terms:
            if term not in flattened:
                flattened.append(term)
    return flattened


def broad_relevance_only(healthcare_hits: list[str], tickers: list[str]) -> bool:
    if tickers:
        return False
    broad_terms = {
        "lilly",
        "cardiovascular",
        "cholesterol",
        "ldl",
        "gene editing",
        "crispr",
        "longevity biotech",
        "cardiometabolic",
    }
    return bool(healthcare_hits) and all(hit in broad_terms for hit in healthcare_hits)


def query_tokens(query: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9\-]+", query.lower())
    return [token for token in tokens if len(token) >= 4 and token not in QUERY_STOPWORDS]


def source_is_low_signal(source: str) -> bool:
    normalized = normalize_text(source)
    return normalized in LOW_SIGNAL_SEARCH_SOURCES


def keyword_candidate_has_evidence(article: dict[str, Any]) -> bool:
    evidence_text = article_evidence_text(article)
    return bool(
        matched_terms(evidence_text, query_tokens(article.get("query", "")))
        or matched_terms(evidence_text, flatten_relevance_terms())
    )


def theme_hit_count(text: str, theme: str) -> int:
    if theme == "Other":
        return 0
    normalized = normalize_text(text)
    return sum(
        1
        for keyword in THEME_KEYWORDS.get(theme, [])
        if re.search(term_pattern(keyword), normalized, flags=re.IGNORECASE)
    )


def specific_healthcare_hits(strong_hits: list[str]) -> list[str]:
    broad_terms = {"lilly", "eli lilly", "obesity drug", "diabetes drug", "cardiovascular", "ldl", "cholesterol"}
    return [hit for hit in strong_hits if hit not in broad_terms]


def ticker_feed_mismatch(article: dict[str, Any], tickers: list[str]) -> bool:
    target_ticker = str(article.get("target_ticker", "")).strip().upper()
    return article.get("feed_kind") == "ticker" and bool(target_ticker) and target_ticker not in tickers


def compute_relevance_score(
    strong_hits: list[str],
    specific_hits: list[str],
    query_hits: list[str],
    tickers: list[str],
    theme: str,
    theme_hits: int,
    exclusion_hits: list[str],
    feed_kind: str,
    target_ticker: str,
    source: str,
) -> float:
    score = 0.0
    score += min(len(strong_hits), 4) * 0.12
    score += min(len(specific_hits), 3) * 0.1
    score += min(len(query_hits), 3) * 0.08
    score += min(len(tickers), 2) * 0.14
    if feed_kind == "ticker" and target_ticker and target_ticker in tickers:
        score += TICKER_FEED_RELEVANCE_BOOST
    if theme != "Other":
        score += 0.1 + min(theme_hits, 3) * 0.03
    if strong_hits and not specific_hits and not tickers:
        score -= 0.12
    if feed_kind == "keyword" and source_is_low_signal(source):
        score -= 0.08
    score -= min(len(exclusion_hits), 2) * 0.1
    return round(max(0.0, min(score, 1.0)), 3)


def evaluate_relevance(article: dict[str, Any]) -> dict[str, Any]:
    age_days = article_age_days(article)
    if age_days is not None and age_days > MAX_NEWS_AGE_DAYS:
        return {
            "accepted": False,
            "rejection_stage": "relevance_gate",
            "rejection_reason": (
                f"Article is {age_days:.1f} days old, which exceeds the {MAX_NEWS_AGE_DAYS}-day news window."
            ),
            "strong_hits": [],
            "specific_hits": [],
            "exclusion_hits": [],
            "query_hits": [],
            "tickers": [],
            "theme": "Other",
            "theme_hits": 0,
            "relevance_score": 0.0,
            "evidence_text": article_evidence_text(article),
        }

    evidence_text = article_evidence_text(article)
    strong_hits = matched_terms(evidence_text, flatten_relevance_terms())
    exclusion_hits = matched_terms(evidence_text, EXCLUSION_TERMS)
    tickers = detect_tickers(evidence_text)
    theme = classify_theme(evidence_text)
    theme_hits = theme_hit_count(evidence_text, theme)
    query_hits = matched_terms(evidence_text, query_tokens(article.get("query", "")))
    specific_hits = specific_healthcare_hits(strong_hits)
    score = compute_relevance_score(
        strong_hits=strong_hits,
        specific_hits=specific_hits,
        query_hits=query_hits,
        tickers=tickers,
        theme=theme,
        theme_hits=theme_hits,
        exclusion_hits=exclusion_hits,
        feed_kind=article.get("feed_kind", "keyword"),
        target_ticker=article.get("target_ticker", ""),
        source=article.get("source", ""),
    )

    if score < MIN_ACCEPTANCE_RELEVANCE_SCORE:
        return {
            "accepted": False,
            "rejection_stage": "relevance_gate",
            "rejection_reason": (
                f"Relevance score {score:.2f} below threshold {MIN_ACCEPTANCE_RELEVANCE_SCORE:.2f}. "
                "Article lacked enough specific healthcare evidence."
            ),
            "strong_hits": strong_hits,
            "specific_hits": specific_hits,
            "exclusion_hits": exclusion_hits,
            "query_hits": query_hits,
            "tickers": tickers,
            "theme": theme,
            "theme_hits": theme_hits,
            "relevance_score": score,
            "evidence_text": evidence_text,
        }

    if exclusion_hits and broad_relevance_only(strong_hits, tickers) and not specific_hits:
        return {
            "accepted": False,
            "rejection_stage": "exclusion_filter",
            "rejection_reason": (
                "Excluded because the article is dominated by generic finance/tech terms and lacks a specific "
                "healthcare entity or product match."
            ),
            "strong_hits": strong_hits,
            "specific_hits": specific_hits,
            "exclusion_hits": exclusion_hits,
            "query_hits": query_hits,
            "tickers": tickers,
            "theme": theme,
            "theme_hits": theme_hits,
            "relevance_score": score,
            "evidence_text": evidence_text,
        }

    if ticker_feed_mismatch(article, tickers) and theme == "Other":
        return {
            "accepted": False,
            "rejection_stage": "relevance_gate",
            "rejection_reason": "Ticker headline did not reference the target ticker and did not map to a thesis theme.",
            "strong_hits": strong_hits,
            "specific_hits": specific_hits,
            "exclusion_hits": exclusion_hits,
            "query_hits": query_hits,
            "tickers": tickers,
            "theme": theme,
            "theme_hits": theme_hits,
            "relevance_score": score,
            "evidence_text": evidence_text,
        }

    if theme == "Other" and len(specific_hits) < 2 and len(query_hits) < 1:
        return {
            "accepted": False,
            "rejection_stage": "relevance_gate",
            "rejection_reason": (
                "Company or ticker mention lacked a strong thesis-specific catalyst, product, or healthcare theme match."
            ),
            "strong_hits": strong_hits,
            "specific_hits": specific_hits,
            "exclusion_hits": exclusion_hits,
            "query_hits": query_hits,
            "tickers": tickers,
            "theme": theme,
            "theme_hits": theme_hits,
            "relevance_score": score,
            "evidence_text": evidence_text,
        }

    return {
        "accepted": True,
        "rejection_stage": None,
        "rejection_reason": "",
        "strong_hits": strong_hits,
        "specific_hits": specific_hits,
        "exclusion_hits": exclusion_hits,
        "query_hits": query_hits,
        "tickers": tickers,
        "theme": theme,
        "theme_hits": theme_hits,
        "relevance_score": score,
        "evidence_text": evidence_text,
    }


def build_articles_frame(articles: list[dict[str, Any]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    accepted_rows = []
    rejected_rows = []

    for article in articles:
        gate = evaluate_relevance(article)
        if not gate["accepted"]:
            rejected_rows.append(
                {
                    **article,
                    "source": article_source(article),
                    "feed_kind": article.get("feed_kind", "keyword"),
                    "target_ticker": article.get("target_ticker", ""),
                    "rejection_stage": gate["rejection_stage"],
                    "rejection_reason": gate["rejection_reason"],
                    "matched_healthcare_terms": ", ".join(gate["strong_hits"]),
                    "matched_specific_terms": ", ".join(gate["specific_hits"]),
                    "matched_exclusion_terms": ", ".join(gate["exclusion_hits"]),
                    "matched_query_terms": ", ".join(gate["query_hits"]),
                    "detected_tickers": ", ".join(gate["tickers"]),
                    "theme_candidate": gate["theme"],
                    "theme_hit_count": gate["theme_hits"],
                    "relevance_score": gate["relevance_score"],
                }
            )
            continue

        combined_text = gate["evidence_text"]
        theme = gate["theme"]
        sentiment, explanation = score_sentiment(combined_text, theme)
        tickers = gate["tickers"]
        accepted_rows.append(
            {
                **article,
                "source": article_source(article),
                "feed_kind": article.get("feed_kind", "keyword"),
                "target_ticker": article.get("target_ticker", ""),
                "theme": theme,
                "sentiment_score": sentiment,
                "sentiment_label": "Positive" if sentiment > 0.15 else "Negative" if sentiment < -0.15 else "Neutral",
                "tickers": ", ".join(tickers),
                "relevance_score": round((gate["relevance_score"] * 0.7) + (relevance_score(theme, tickers, sentiment, gate["strong_hits"]) * 0.3), 3),
                "explanation": explanation,
                "matched_healthcare_terms": ", ".join(gate["strong_hits"]),
                "matched_specific_terms": ", ".join(gate["specific_hits"]),
                "matched_exclusion_terms": ", ".join(gate["exclusion_hits"]),
                "matched_query_terms": ", ".join(gate["query_hits"]),
            }
        )

    accepted_df = pd.DataFrame(accepted_rows)
    rejected_df = pd.DataFrame(rejected_rows)

    if accepted_df.empty:
        accepted_df = pd.DataFrame(
            columns=[
                "query",
                "feed_url",
                "title",
                "summary",
                "url",
                "source",
                "rss_metadata",
                "feed_kind",
                "target_ticker",
                "published_at",
                "theme",
                "sentiment_score",
                "sentiment_label",
                "tickers",
                "relevance_score",
                "explanation",
                "matched_healthcare_terms",
                "matched_specific_terms",
                "matched_exclusion_terms",
                "matched_query_terms",
            ]
        )
    else:
        accepted_df["published_at"] = pd.to_datetime(accepted_df["published_at"], utc=True, errors="coerce")
        accepted_df = accepted_df.sort_values(
            ["relevance_score", "published_at"],
            ascending=[False, False],
            na_position="last",
        ).reset_index(drop=True)

    if rejected_df.empty:
        rejected_df = pd.DataFrame(
            columns=[
                "query",
                "feed_url",
                "title",
                "summary",
                "url",
                "source",
                "rss_metadata",
                "feed_kind",
                "target_ticker",
                "published_at",
                "rejection_stage",
                "rejection_reason",
                "matched_healthcare_terms",
                "matched_specific_terms",
                "matched_exclusion_terms",
                "matched_query_terms",
                "detected_tickers",
                "theme_candidate",
                "theme_hit_count",
                "relevance_score",
            ]
        )
    else:
        rejected_df["published_at"] = pd.to_datetime(rejected_df["published_at"], utc=True, errors="coerce")
        rejected_df = rejected_df.sort_values("published_at", ascending=False, na_position="last").reset_index(drop=True)

    return accepted_df, rejected_df


def summarize_themes(articles_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if articles_df.empty:
        empty = pd.DataFrame(columns=["theme", "story_count", "avg_sentiment"])
        return empty, pd.DataFrame(columns=["sentiment_label", "story_count"])

    theme_summary = (
        articles_df.groupby("theme")
        .agg(story_count=("title", "count"), avg_sentiment=("sentiment_score", "mean"))
        .sort_values(["story_count", "avg_sentiment"], ascending=[False, False])
        .reset_index()
    )
    sentiment_summary = (
        articles_df.groupby("sentiment_label")
        .agg(story_count=("title", "count"))
        .reset_index()
        .sort_values("story_count", ascending=False)
    )
    return theme_summary, sentiment_summary


def summarize_tickers(articles_df: pd.DataFrame) -> pd.DataFrame:
    if articles_df.empty:
        return pd.DataFrame(columns=["ticker", "story_count"])
    exploded = (
        articles_df.assign(ticker=articles_df["tickers"].str.split(r",\s*"))
        .explode("ticker")
    )
    exploded = exploded[exploded["ticker"].notna() & (exploded["ticker"] != "")]
    if exploded.empty:
        return pd.DataFrame(columns=["ticker", "story_count"])
    return (
        exploded.groupby("ticker")
        .agg(story_count=("title", "count"))
        .sort_values("story_count", ascending=False)
        .reset_index()
    )


def fetch_news_snapshot(write_raw_json: bool = True) -> NewsSnapshot:
    fetched_articles: list[dict[str, Any]] = []
    fetch_errors: list[str] = []

    for query in NEWS_QUERIES:
        try:
            fetched_articles.extend(fetch_feed(query))
        except Exception as exc:
            fetch_errors.append(f"{query}: {exc}")

    for ticker in NEWS_TICKERS:
        try:
            fetched_articles.extend(fetch_ticker_feed(ticker))
        except Exception as exc:
            fetch_errors.append(f"ticker:{ticker}: {exc}")

    deduped = deduplicate_articles(fetched_articles)
    articles_df, rejected_df = build_articles_frame(deduped)
    theme_summary, sentiment_summary = summarize_themes(articles_df)
    accepted_by_theme = theme_summary[["theme", "story_count"]].copy() if not theme_summary.empty else pd.DataFrame(columns=["theme", "story_count"])
    accepted_by_ticker = summarize_tickers(articles_df)

    raw_payload_path: Path | None = None
    if write_raw_json:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        raw_payload_path = RAW_DIR / f"rss_articles_{timestamp}.json"
        raw_payload_path.write_text(json.dumps(deduped, indent=2), encoding="utf-8")

    rejected_by_relevance_gate = int((rejected_df["rejection_stage"] == "relevance_gate").sum()) if not rejected_df.empty else 0
    rejected_by_exclusion_filter = int((rejected_df["rejection_stage"] == "exclusion_filter").sum()) if not rejected_df.empty else 0

    return NewsSnapshot(
        articles=articles_df,
        rejected_articles=rejected_df,
        theme_summary=theme_summary,
        sentiment_summary=sentiment_summary,
        fetch_errors=fetch_errors,
        raw_payload_path=raw_payload_path,
        total_fetched=len(deduped),
        rejected_by_relevance_gate=rejected_by_relevance_gate,
        rejected_by_exclusion_filter=rejected_by_exclusion_filter,
        accepted_story_count=len(articles_df),
        accepted_by_theme=accepted_by_theme,
        accepted_by_ticker=accepted_by_ticker,
    )
