"""Tests for IOCL Certified Query Library (Q01-Q30) and Semantic Router."""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.router import get_semantic_router
from app.tools.certified_query import (
    get_certified_entry,
    list_certified_queries,
    run_certified_query,
)


def test_certified_library_loading():
    """Verifies that all 30 IOCL certified queries Q01-Q30 are loaded with provenance."""
    queries = list_certified_queries()
    assert len(queries) == 30, f"Expected 30 queries, found {len(queries)}"

    entry_q01 = get_certified_entry("Q01")
    assert entry_q01 is not None
    assert entry_q01["id"] == "Q01"
    assert "fiscal_year" in entry_q01["params"]
    assert entry_q01["provenance"]["source_file"] == "financial_build/iocl_certified/Q01.sql"
    assert len(entry_q01["provenance"]["sha256"]) == 64

    # Backward compatibility alias check
    assert get_certified_entry("C1")["id"] == "Q01"


def test_certified_q01_execution():
    """Verifies Q01 execution returns verified IOCL FY26 Schedule III P&L."""
    res = run_certified_query("Q01", persona="CMD")
    assert res.get("type") == "certified_query_result"
    assert res.get("query_id") == "Q01"
    rows = res.get("rows", [])
    assert len(rows) > 10
    pat_row = next((r for r in rows if r.get("line_code") == "pat_inr_cr"), None)
    assert pat_row is not None
    assert abs(float(pat_row["amount_inr_cr"]) - 36802.42) < 0.05


def test_certified_q07_execution():
    """Verifies Q07 execution returns all 9 IOCL refineries ranked by GRM."""
    res = run_certified_query("Q07", persona="CMD")
    assert res.get("type") == "certified_query_result"
    assert res.get("query_id") == "Q07"
    assert res.get("row_count") == 9
    names = {r["refinery_id"] for r in res.get("rows", [])}
    assert {"REF-PNP", "REF-PRD", "REF-KYL", "REF-MTR", "REF-HLD", "REF-BRN", "REF-BNG", "REF-GHY", "REF-DGB"} == names


def test_certified_parameter_override():
    """Verifies that fiscal_year override works dynamically on certified queries."""
    res_fy25 = run_certified_query("Q07", params={"fiscal_year": "FY25"}, persona="CMD")
    assert res_fy25.get("type") == "certified_query_result"
    assert res_fy25.get("params_applied", {}).get("fiscal_year") == "FY25"
    assert res_fy25.get("row_count") == 9


def test_semantic_router_canonical_match():
    """Verifies that canonical IOCL questions route above threshold to certified queries."""
    router = get_semantic_router()
    decision = router.route("Show the Schedule III Profit and Loss statement of IOCL for FY26")
    assert decision["route"] == "certified"
    assert decision["query_id"] == "Q01"
    assert decision["score"] >= 0.70


def test_semantic_router_novel_prompt_fallback():
    """Verifies that an out-of-distribution prompt routes to live_nl_sql."""
    router = get_semantic_router()
    decision = router.route("What would happen if green hydrogen electrolyzer capex falls 60% in 2042?")
    assert decision["route"] == "live_nl_sql"
    assert decision["query_id"] is None
