from __future__ import annotations

import importlib.util
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
REPORTS_DIR = OUTPUT_DIR / "reports"
RAW_DIR = OUTPUT_DIR / "raw"
CLASSIFIED_DIR = OUTPUT_DIR / "classified"
HISTORY_DIR = OUTPUT_DIR / "history"
VALIDATION_DIR = OUTPUT_DIR / "validation"
CACHE_DIR = RAW_DIR / "cache"

BENCHMARKS = ["XLV", "XBI", "IBB", "ARKG", "QQQ", "SPY"]

TICKER_GROUPS = {
    "Core GLP-1 Leaders": ["LLY", "NVO"],
    "GLP-1 Challengers": ["AMGN", "VKTX", "ALT", "GPCR", "PFE", "RHHBY"],
    "Large Pharma AI Adopters": ["MRK", "ABBV", "BMY", "GSK", "SNY", "AZN", "JNJ"],
    "AI Drug Discovery Platforms": ["RXRX", "SDGR", "ABCL", "CERT", "DNA", "TEM"],
    "Gene Editing / Cardiometabolic Adjacent": ["CRSP", "NTLA", "BEAM", "EDIT", "REGN", "VRTX"],
    "AI Infrastructure Enablers": ["NVDA", "TSM", "AVGO", "SMH", "SOXX"],
    "Healthcare Benchmarks": BENCHMARKS,
}

TICKER_EXCEPTIONS = {
    "EXAI": {
        "action": "drop",
        "reason": "Exscientia went private and should stay out of the live ticker universe.",
    },
}

NEWS_QUERIES = [
    "Eli Lilly Zepbound obesity",
    "Eli Lilly Mounjaro diabetes",
    "orforglipron Eli Lilly",
    "retatrutide Eli Lilly",
    "tirzepatide obesity trial",
    "semaglutide obesity trial",
    "Novo Nordisk Wegovy obesity",
    "Novo Nordisk Ozempic semaglutide",
    "Viking Therapeutics VK2735 obesity",
    "Amgen MariTide obesity",
    "Altimmune pemvidutide obesity",
    "Structure Therapeutics GSBR-1290 obesity",
    "Eli Lilly AI drug discovery",
    "Isomorphic Labs Eli Lilly",
    "Insilico Medicine Eli Lilly",
    "Recursion AI drug discovery",
    "Schrodinger drug discovery AI",
    "Chai Discovery Pfizer Eli Lilly",
    "Verve Therapeutics LDL gene editing",
    "CRISPR cardiovascular LDL",
]

NEWS_TICKERS = [
    "LLY",
    "NVO",
    "AMGN",
    "VKTX",
    "ALT",
    "GPCR",
    "RXRX",
    "SDGR",
    "ABCL",
    "CRSP",
    "NTLA",
    "BEAM",
    "NVDA",
]

STRONG_RELEVANCE_TERMS = {
    "GLP-1 / Obesity": [
        "glp-1",
        "obesity drug",
        "weight-loss drug",
        "diabetes drug",
        "tirzepatide",
        "semaglutide",
        "retatrutide",
        "orforglipron",
        "zepbound",
        "mounjaro",
        "ozempic",
        "wegovy",
    ],
    "Company / Product": [
        "eli lilly",
        "lilly",
        "lly",
        "novo nordisk",
        "nvo",
        "viking therapeutics",
        "vktx",
        "amgen",
        "amgn",
        "altimmune",
        "alt",
        "structure therapeutics",
        "gpcr",
    ],
    "AI Health": [
        "ai drug discovery",
        "computational biology",
        "protein design",
        "ai biotech",
        "insilico",
        "isomorphic labs",
        "recursion",
        "rxrx",
        "schrodinger",
        "schrodinger",
        "sdgr",
        "abcellera",
        "abcl",
        "chai discovery",
        "lillypad",
        "lilly pad",
        "lilly pod",
        "tune lab",
    ],
    "Longevity / Cardiometabolic": [
        "longevity biotech",
        "cardiometabolic",
        "cardiovascular",
        "ldl",
        "cholesterol",
        "gene editing",
        "crispr",
        "verve therapeutics",
        "crsp",
        "ntla",
        "beam",
    ],
}

EXCLUSION_TERMS = [
    "gold",
    "grain",
    "grains",
    "commodities",
    "commodity",
    "crypto",
    "bitcoin",
    "fed policy",
    "federal reserve",
    "inflation expectations",
    "banking",
    "bank",
    "tax",
    "taxes",
    "personal finance",
    "amd",
    "advanced micro devices",
    "ai hiring",
    "hiring",
    "cloud expansion",
    "cloud capex",
    "tech funding",
    "generic ai",
]

THEME_KEYWORDS = {
    "GLP-1 Demand": ["glp-1", "zepbound", "mounjaro", "obesity", "weight loss", "tirzepatide", "semaglutide"],
    "GLP-1 Competition": ["novo", "amgen", "viking", "challenger", "share", "competition"],
    "Lilly AI Infrastructure": ["ai infrastructure", "data center", "gpu", "nvidia", "lilly pad", "lillypod", "model"],
    "Lilly M&A / IP Acquisition": ["acquisition", "deal", "m&a", "buyout", "licensing", "partner"],
    "AI Drug Discovery": ["drug discovery", "insilico", "isomorphic", "chai", "recursion", "schrodinger", "ai biotech"],
    "Longevity": ["longevity", "aging", "anti-aging", "lifespan"],
    "Cardiovascular / Gene Editing": ["cardio", "cholesterol", "ldl", "gene editing", "crispr", "verve", "heart"],
    "Obesity Policy / Pricing": ["pricing", "reimbursement", "policy", "coverage", "medicare", "cost"],
    "Side Effects / Safety": ["side effect", "adverse", "safety", "warning", "risk", "lawsuit"],
    "Regulatory Risk": ["fda", "regulatory", "approval", "complete response", "hold", "delay"],
    "Manufacturing / Supply": ["supply", "manufacturing", "shortage", "capacity", "plant"],
    "Consumer Behavior Impact": ["consumer", "food", "restaurant", "spending", "behavior"],
    "Healthcare Cost Reduction": ["healthcare cost", "cost reduction", "savings", "chronic disease", "benefit"],
}

POSITIVE_TERMS = [
    "approval",
    "breakthrough",
    "demand",
    "expansion",
    "trial success",
    "positive data",
    "revenue growth",
    "partnership",
    "acquisition",
    "ai model",
    "drug discovery",
    "longevity",
    "cardiovascular benefit",
    "addiction benefit",
    "supply expansion",
    "price reduction",
    "market share gain",
]

NEGATIVE_TERMS = [
    "side effects",
    "safety concern",
    "lawsuit",
    "regulatory warning",
    "pricing pressure",
    "supply shortage",
    "trial failure",
    "competition",
    "patent risk",
    "reimbursement risk",
    "political pressure",
    "slowdown",
    "downgrade",
]

THEME_SENTIMENT_BIAS = {
    "GLP-1 Demand": 0.25,
    "Lilly AI Infrastructure": 0.25,
    "Lilly M&A / IP Acquisition": 0.15,
    "AI Drug Discovery": 0.15,
    "Healthcare Cost Reduction": 0.1,
    "Side Effects / Safety": -0.4,
    "Regulatory Risk": -0.25,
    "Obesity Policy / Pricing": -0.1,
    "Manufacturing / Supply": -0.1,
}

TICKER_ALIASES = {
    "LLY": ["eli lilly", "lilly", "zepbound", "mounjaro", "tirzepatide"],
    "NVO": ["novo nordisk", "wegovy", "ozempic", "semaglutide"],
    "AMGN": ["amgen"],
    "VKTX": ["viking therapeutics", "viking"],
    "ALT": ["altimmune"],
    "GPCR": ["structure therapeutics"],
    "RXRX": ["recursion"],
    "SDGR": ["schrodinger"],
    "ABCL": ["abcellera"],
    "TEM": ["tempus"],
    "CRSP": ["crispr"],
    "NTLA": ["intellia", "intellia therapeutics"],
    "BEAM": ["beam therapeutics"],
    "EDIT": ["editas"],
    "REGN": ["regeneron"],
    "VRTX": ["vertex"],
    "MRK": ["merck"],
    "ABBV": ["abbvie"],
    "BMY": ["bristol myers", "bristol-myers"],
    "AZN": ["astrazeneca"],
    "JNJ": ["johnson & johnson", "johnson and johnson"],
    "NVDA": ["nvidia"],
    "PFE": ["pfizer"],
    "RHHBY": ["roche"],
}

RS_COMPARATORS = ["XLV", "QQQ", "SPY"]
LLY_COMPARATORS = ["NVO", "XLV", "XBI", "QQQ", "NVDA"]
LOOKBACK_DAYS = 400


def _load_local_overrides() -> None:
    local_path = BASE_DIR / "config.local.py"
    if not local_path.exists():
        return

    spec = importlib.util.spec_from_file_location("glp1_watch_local_config", local_path)
    if spec is None or spec.loader is None:
        return

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    for name in dir(module):
        if not name.isupper():
            continue
        globals()[name] = getattr(module, name)


_load_local_overrides()
