"""Tests for Phase 1 sleeve configuration loading and validation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from glp1_watch.health_stack_sleeves import (
    EXPECTED_REQUIRED_SLEEVES,
    Sleeve,
    core_breadth_tickers,
    load_sleeve_config,
    required_sleeves,
    ticker_to_sleeve_map,
)


def _write_yaml(tmp_dir: str, body: str) -> Path:
    path = Path(tmp_dir) / "sleeves.yaml"
    path.write_text(body, encoding="utf-8")
    return path


MINIMAL_VALID = """\
sleeves:
  - name: "Established GLP-1 Leaders"
    tickers: ["LLY", "NVO"]
    required: true
  - name: "Emerging GLP-1 Challengers"
    tickers: ["AMGN", "VKTX", "ALT", "GPCR", "PFE", "RHHBY"]
    required: true
  - name: "Large-Pharma GLP-1 Optionality"
    tickers: ["MRK", "ABBV", "BMY", "GSK", "SNY", "AZN", "JNJ"]
    required: true
  - name: "AI Drug-Discovery Platforms"
    tickers: ["RXRX", "SDGR", "ABCL", "DNA"]
    required: true
  - name: "Gene Editing and Precision Medicine"
    tickers: ["CRSP", "NTLA", "BEAM", "EDIT", "REGN", "VRTX"]
    required: true
  - name: "Health Data and Clinical AI"
    tickers: ["TEM", "CERT"]
    required: true
  - name: "Broad Biotech Risk Appetite"
    tickers: ["XBI", "IBB", "ARKG"]
    required: true
  - name: "AI Infrastructure Enablers"
    tickers: ["NVDA", "TSM", "AVGO", "SMH", "SOXX"]
    required: false
"""


class SleeveConfigTests(unittest.TestCase):
    def test_loads_bundled_config_with_eight_sleeves(self) -> None:
        sleeves = load_sleeve_config()
        self.assertEqual(len(sleeves), 8)
        self.assertEqual(
            frozenset(s.name for s in sleeves if s.required), EXPECTED_REQUIRED_SLEEVES
        )
        supporting = [s for s in sleeves if not s.required]
        self.assertEqual(len(supporting), 1)
        self.assertEqual(supporting[0].name, "AI Infrastructure Enablers")

    def test_ticker_to_sleeve_map(self) -> None:
        sleeves = load_sleeve_config()
        mapping = ticker_to_sleeve_map(sleeves)
        self.assertEqual(mapping["LLY"], "Established GLP-1 Leaders")
        self.assertEqual(mapping["NVDA"], "AI Infrastructure Enablers")
        self.assertEqual(mapping["TEM"], "Health Data and Clinical AI")
        # No ticker appears twice: map size equals total membership.
        total = sum(len(s.tickers) for s in sleeves)
        self.assertEqual(len(mapping), total)

    def test_core_breadth_tickers_exclude_supporting_sleeve(self) -> None:
        sleeves = load_sleeve_config()
        core = core_breadth_tickers(sleeves)
        self.assertIn("LLY", core)
        self.assertIn("TEM", core)
        for ticker in ("NVDA", "TSM", "AVGO", "SMH", "SOXX"):
            self.assertNotIn(ticker, core)
        required_total = sum(len(s.tickers) for s in required_sleeves(sleeves))
        self.assertEqual(len(core), required_total)

    def test_missing_file_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            load_sleeve_config("/nonexistent/sleeves.yaml")

    def test_rejects_duplicate_ticker_membership(self) -> None:
        body = """\
sleeves:
  - name: "Sleeve A"
    tickers: ["LLY", "NVO"]
    required: true
  - name: "Sleeve B"
    tickers: ["NVO", "AMGN"]
    required: false
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = _write_yaml(tmp_dir, body)
            with self.assertRaisesRegex(ValueError, "Duplicate ticker membership"):
                load_sleeve_config(path)

    def test_rejects_unknown_ticker(self) -> None:
        body = """\
sleeves:
  - name: "Sleeve A"
    tickers: ["LLY", "FAKETICKER"]
    required: true
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = _write_yaml(tmp_dir, body)
            with self.assertRaisesRegex(ValueError, "unknown ticker"):
                load_sleeve_config(path)

    def test_rejects_comparator_as_sleeve_member(self) -> None:
        body = """\
sleeves:
  - name: "Sleeve A"
    tickers: ["LLY", "XLV"]
    required: true
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = _write_yaml(tmp_dir, body)
            with self.assertRaisesRegex(ValueError, "comparator"):
                load_sleeve_config(path)

    def test_rejects_empty_ticker_list(self) -> None:
        body = """\
sleeves:
  - name: "Sleeve A"
    tickers: []
    required: true
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = _write_yaml(tmp_dir, body)
            with self.assertRaisesRegex(ValueError, "non-empty"):
                load_sleeve_config(path)

    def test_rejects_wrong_required_set(self) -> None:
        # Valid membership, but the required set does not match the expected seven.
        body = MINIMAL_VALID.replace(
            '- name: "AI Infrastructure Enablers"\n    tickers: ["NVDA", "TSM", "AVGO", "SMH", "SOXX"]\n    required: false',
            '- name: "AI Infrastructure Enablers"\n    tickers: ["NVDA", "TSM", "AVGO", "SMH", "SOXX"]\n    required: true',
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = _write_yaml(tmp_dir, body)
            with self.assertRaisesRegex(ValueError, "Required sleeve set mismatch"):
                load_sleeve_config(path)

    def test_sleeve_dataclass_fields(self) -> None:
        sleeve = Sleeve(name="Test", tickers=("LLY",), required=True, description="d")
        self.assertEqual(sleeve.name, "Test")
        self.assertEqual(sleeve.tickers, ("LLY",))
        self.assertTrue(sleeve.required)
