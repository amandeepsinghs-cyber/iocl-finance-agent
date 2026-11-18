"""IOCL SSOT compiler verification tests: BigQuery & local_snapshot parity, vintage rules, poisoned-row filter, and provenance."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import pytest

from app.brain.compiler import Compiler
from app.brain.planner import Period, QuerySpec
from app.brain.pipeline import run_planner_turn
from app.brain.presenter import build_visual
from app.session_memory import get_session_manager

FIXTURE_MIN_PARQUET = Path(__file__).resolve().parent / "fixtures" / "fact_snapshot_min.parquet"

# Verified IOCL Standalone Annual Report Cases (FY17-FY26)
FINANCE_CASES: List[Dict[str, Any]] = [
    {
        "id": "F01",
        "spec": QuerySpec(metric="corporate_revenue_cr", period=Period(fy="FY24")),
        "col": "corporate_revenue_cr",
        "expected": {None: 866345.38},
        "tol": 0.05,
        "provenance": "verified_ar",
        "doc": "IOCL_AR_FY2023-24.pdf",
        "page_label": "109",
    },
    {
        "id": "F02",
        "spec": QuerySpec(metric="pat_cr", period=Period(fy="FY24")),
        "col": "pat_cr",
        "expected": {None: 39618.84},
        "tol": 0.05,
        "provenance": "verified_ar",
        "doc": "IOCL_AR_FY2023-24.pdf",
        "page_label": "109",
    },
    {
        "id": "F03",
        "spec": QuerySpec(metric="tax_expense_cr", period=Period(fy="FY25")),
        "col": "tax_expense_cr",
        "expected": {None: 2920.77},
        "tol": 0.05,
        "provenance": "verified_ar",
        "doc": "IOCL_AR_FY2024-25.pdf",
        "page_label": "210",
    },
    {
        "id": "F04",
        "spec": QuerySpec(metric="pbt_corporate_cr", period=Period(fy="FY26")),
        "col": "pbt_corporate_cr",
        "expected": {None: 48784.41},
        "tol": 0.05,
        "provenance": "verified_ar",
        "doc": "IOCL_AR_FY2025-26.pdf",
        "page_label": "205",
    },
    {
        "id": "F07",
        "spec": QuerySpec(metric="total_assets_cr", period=Period(fy="FY26")),
        "col": "total_assets_cr",
        "expected": {None: 491535.12},
        "tol": 0.05,
        "provenance": "verified_ar",
        "doc": "IOCL_AR_FY2025-26.pdf",
        "page_label": "203",
    },
    {
        "id": "F08",
        "spec": QuerySpec(metric="operating_cash_flow_cr", period=Period(fy="FY25")),
        "col": "operating_cash_flow_cr",
        "expected": {None: 33170.46},
        "tol": 0.05,
        "provenance": "verified_ar",
    },
    {
        "id": "F09",
        "spec": QuerySpec(metric="operating_cash_flow_cr", period=Period(fy="FY24")),
        "col": "operating_cash_flow_cr",
        "expected": {None: 68096.60},
        "tol": 0.05,
        "provenance": "verified_ar",
    },
    {
        "id": "F10",
        "spec": QuerySpec(metric="operating_cash_flow_cr", period=Period(fy="FY26")),
        "col": "operating_cash_flow_cr",
        "expected": {None: 71398.57},
        "tol": 0.05,
        "provenance": "verified_ar",
    },
    {
        "id": "F11",
        "spec": QuerySpec(metric="cash_and_bank_cr", period=Period(fy="FY26")),
        "col": "cash_and_bank_cr",
        "expected": {None: 281.41},
        "tol": 0.05,
        "provenance": "verified_ar",
    },
    {
        "id": "F13",
        "spec": QuerySpec(
            metric="corporate_revenue_cr",
            period=Period(from_="FY17", to="FY26"),
            dimensions=["fy"],
        ),
        "col": "corporate_revenue_cr",
        "expected": {
            "FY17": 445441.90,
            "FY18": 506427.59,
            "FY19": 605932.34,
            "FY20": 566353.55,
            "FY21": 514890.47,
            "FY22": 728445.40,
            "FY23": 934952.66,
            "FY24": 866345.38,
            "FY25": 845512.61,
            "FY26": 886224.41,
        },
        "tol": 0.10,
        "provenance": "verified_ar",
    },
    {
        "id": "F14",
        "spec": QuerySpec(
            metric="pat_cr",
            period=Period(from_="FY22", to="FY26"),
            dimensions=["fy"],
        ),
        "col": "pat_cr",
        "expected": {
            "FY22": 24184.10,
            "FY23": 8241.82,
            "FY24": 39618.84,
            "FY25": 12961.57,
            "FY26": 36802.42,
        },
        "tol": 0.10,
        "provenance": "verified_ar",
    },
    {
        "id": "F15",
        "spec": QuerySpec(metric="roce_pct", period=Period(fy="FY23")),
        "col": "roce_pct",
        "expected": {None: 6.22},
        "tol": 0.05,
        "provenance": "verified_ar",
    },
    {
        "id": "F16",
        "spec": QuerySpec(
            metric="roce_pct",
            period=Period(from_="FY22", to="FY26"),
            dimensions=["fy"],
        ),
        "col": "roce_pct",
        "expected": {
            "FY22": 15.10,
            "FY23": 6.22,
            "FY24": 20.35,
            "FY25": 7.27,
            "FY26": 18.00,
        },
        "tol": 0.05,
        "provenance": "verified_ar",
    },
    {
        "id": "F18",
        "spec": QuerySpec(metric="excise_duty_cr", period=Period(fy="FY24")),
        "col": "excise_duty_cr",
        "expected": {None: 91996.79},
        "tol": 0.10,
        "provenance": "verified_ar",
    },
    {
        "id": "F20",
        "spec": QuerySpec(metric="capex_actual_cr", period=Period(fy="FY25")),
        "col": "capex_actual_cr",
        "expected": {None: 33494.28},
        "tol": 0.10,
        "provenance": "verified_ar",
    },
    {
        "id": "F21",
        "spec": QuerySpec(
            metric="capex_actual_cr",
            period=Period(from_="FY17", to="FY26"),
            dimensions=["fy"],
        ),
        "col": "capex_actual_cr",
        "expected": {
            "FY17": 13979.42,
            "FY18": 17185.82,
            "FY19": 22356.41,
            "FY20": 30394.35,
            "FY21": 21161.82,
            "FY22": 22137.01,
            "FY23": 31250.46,
            "FY24": 35209.07,
            "FY25": 33494.28,
            "FY26": 26421.09,
        },
        "tol": 0.10,
        "provenance": "verified_ar",
    },
    {
        "id": "F23",
        "spec": QuerySpec(metric="debt_to_equity_ratio", period=Period(fy="FY26")),
        "col": "debt_to_equity_ratio",
        "expected": {None: 0.54},
        "tol": 0.01,
        "provenance": "verified_ar",
    },
    {
        "id": "F24",
        "spec": QuerySpec(metric="total_debt_cr", period=Period(fy="FY26")),
        "col": "total_debt_cr",
        "expected": {None: 110668.22},
        "extra_cols": {"lease_liabilities_cr": 8545.60},
        "tol": 0.10,
        "provenance": "verified_ar",
    },
    {
        "id": "F26",
        "spec": QuerySpec(metric="dda_cr", period=Period(fy="FY26")),
        "col": "dda_cr",
        "expected": {None: 16964.82},
        "tol": 0.05,
        "provenance": "verified_ar",
        "doc": "IOCL_AR_FY2025-26.pdf",
        "page_label": "205",
    },
    {
        "id": "F27",
        "spec": QuerySpec(metric="finance_costs_cr", period=Period(fy="FY24")),
        "col": "finance_costs_cr",
        "expected": {None: 7327.79},
        "tol": 0.05,
        "provenance": "verified_ar",
        "doc": "IOCL_AR_FY2023-24.pdf",
        "page_label": "109",
    },
    {
        "id": "F28",
        "spec": QuerySpec(metric="other_income_cr", period=Period(fy="FY24")),
        "col": "other_income_cr",
        "expected": {None: 4780.82},
        "tol": 0.05,
        "provenance": "verified_ar",
        "expect_is_restated": False,
        "doc": "IOCL_AR_FY2023-24.pdf",
        "page_label": "109",
    },
    {
        "id": "F29",
        "spec": QuerySpec(
            metric="other_income_cr",
            period=Period(from_="FY24", to="FY26"),
            dimensions=["fy"],
        ),
        "col": "other_income_cr",
        "expected": {"FY24": 4780.82, "FY25": 4963.84, "FY26": 4988.31},
        "tol": 0.10,
        "provenance": "verified_ar",
    },
    {
        "id": "F30",
        "spec": QuerySpec(metric="pat_cr", period=Period(fy="FY19")),
        "col": "pat_cr",
        "expected": {None: 16894.15},
        "tol": 0.10,
        "provenance": "verified_ar",
        "expect_is_restated": False,
    },
    {
        "id": "F31",
        "spec": QuerySpec(
            metric="gross_refining_margin_usd_bbl",
            period=Period(from_="FY22", to="FY26"),
            dimensions=["fy"],
        ),
        "col": "gross_refining_margin_usd_bbl",
        "expected": {"FY22": 11.25, "FY23": 19.52, "FY24": 12.05, "FY25": 4.80, "FY26": 10.85},
        "tol": 0.05,
        "provenance": "verified_ar",
    },
    {
        "id": "F32",
        "spec": QuerySpec(metric="corporate_refining_throughput_mmt", period=Period(fy="FY26")),
        "col": "corporate_refining_throughput_mmt",
        "expected": {None: 75.451},
        "tol": 0.01,
        "provenance": "verified_ar",
    },
]


@pytest.mark.parametrize("mode", ["bigquery", "local_snapshot"])
@pytest.mark.parametrize("case", FINANCE_CASES, ids=[c["id"] for c in FINANCE_CASES])
def test_finance_cases_compiler_and_provenance(
    monkeypatch: pytest.MonkeyPatch, mode: str, case: Dict[str, Any]
) -> None:
    """Verify IOCL financial cases return exact SSOT values in both live BigQuery and local_snapshot modes."""
    if mode == "local_snapshot":
        monkeypatch.setenv("YUKTI_FORCE_BQ_FAIL", "1")
    else:
        if os.getenv("YUKTI_LIVE_BQ") != "1":
            pytest.skip("live BigQuery test (set YUKTI_LIVE_BQ=1)")
        monkeypatch.delenv("YUKTI_FORCE_BQ_FAIL", raising=False)

    comp = Compiler()
    compiled = comp.compile(case["spec"])
    res = asyncio.run(comp.execute(compiled))

    assert res.source == mode, f"{case['id']} ({mode}): expected source={mode}, got {res.source}"
    assert len(res.rows) >= 1, f"{case['id']} ({mode}): returned 0 rows"

    col = case["col"]
    tol = case["tol"]
    expected_map: Dict[Optional[str], float] = case["expected"]

    if None in expected_map:
        r0 = res.rows[0]
        actual = float(r0[col])
        exp = expected_map[None]
        assert abs(actual - exp) <= tol, f"{case['id']} ({mode}): expected {exp} ± {tol}, got {actual}"
        for extra_c, extra_exp in (case.get("extra_cols") or {}).items():
            assert abs(float(r0[extra_c]) - extra_exp) <= tol, (
                f"{case['id']} ({mode}) extra col {extra_c}: expected {extra_exp}, got {r0.get(extra_c)}"
            )
        if "expect_is_restated" in case:
            assert bool(r0.get("is_restated")) is case["expect_is_restated"]
        if mode == "bigquery" and "doc" in case:
            assert r0.get("source_doc") == case["doc"]
            assert str(r0.get("source_page_label")) == case["page_label"]
    else:
        by_fy = {str(r["fiscal_year"]): r for r in res.rows}
        for fy_k, exp_v in expected_map.items():
            assert fy_k in by_fy, f"{case['id']} ({mode}): missing {fy_k} in {list(by_fy.keys())}"
            actual = float(by_fy[fy_k][col])
            assert abs(actual - exp_v) <= tol, (
                f"{case['id']} ({mode}) {fy_k}: expected {exp_v} ± {tol}, got {actual}"
            )


@pytest.mark.parametrize("mode", ["bigquery", "local_snapshot"])
def test_f06_balance_sheet_2024_and_statement_columns(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    """Verify FY24 Balance Sheet returns exact Total Assets, Total Equity, and required columns."""
    if mode == "local_snapshot":
        monkeypatch.setenv("YUKTI_FORCE_BQ_FAIL", "1")
    else:
        if os.getenv("YUKTI_LIVE_BQ") != "1":
            pytest.skip("live BigQuery test (set YUKTI_LIVE_BQ=1)")
        monkeypatch.delenv("YUKTI_FORCE_BQ_FAIL", raising=False)

    comp = Compiler()
    spec = QuerySpec(metric="balance_sheet", period=Period(fy="FY24"))
    compiled = comp.compile(spec)
    res = asyncio.run(comp.execute(compiled))

    assert res.source == mode
    required_cols = {
        "line_code",
        "display_name",
        "level",
        "line_kind",
        "fiscal_year",
        "value_inr_cr",
        "is_restated",
        "source_doc",
        "source_page_label",
    }
    assert required_cols.issubset(set(res.columns)), f"Missing required §5.1 columns: {required_cols - set(res.columns)}"

    by_code = {str(r["line_code"]): r for r in res.rows}
    assert abs(float(by_code["BS.TOTAL_ASSETS"]["value_inr_cr"]) - 457240.62) <= 0.05
    assert abs(float(by_code["BS.EQUITY.TOTAL"]["value_inr_cr"]) - 176714.98) <= 0.05
    assert by_code["BS.TOTAL_ASSETS"]["source_doc"] == "IOCL_AR_FY2023-24.pdf"
    assert str(by_code["BS.TOTAL_ASSETS"]["source_page_label"]) == "108"


def test_poisoned_unverified_row_never_served(monkeypatch: pytest.MonkeyPatch) -> None:
    """Poisoned row (verified=FALSE) in fact_snapshot_min.parquet is never served."""
    assert FIXTURE_MIN_PARQUET.exists(), f"Missing fixture {FIXTURE_MIN_PARQUET}"
    monkeypatch.setenv("YUKTI_FORCE_BQ_FAIL", "1")
    monkeypatch.setenv("YUKTI_FIN_SNAPSHOT_PATH", str(FIXTURE_MIN_PARQUET))

    comp = Compiler()
    spec_rev = QuerySpec(metric="corporate_revenue_cr", period=Period(fy="FY24"))
    res_rev = asyncio.run(comp.execute(comp.compile(spec_rev)))
    assert len(res_rev.rows) == 1
    assert abs(float(res_rev.rows[0]["corporate_revenue_cr"]) - 138402.13) <= 0.05

    spec_pnl = QuerySpec(metric="pnl_statement", period=Period(fy="FY24"))
    res_pnl = asyncio.run(comp.execute(comp.compile(spec_pnl)))
    codes = {str(r["line_code"]) for r in res_pnl.rows}
    assert "PL.POISON_UNVERIFIED" not in codes
    for r in res_pnl.rows:
        assert float(r["value_inr_cr"]) != 999999.99


def test_pipeline_provenance_and_no_ebitda_synthesis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify IOCL pipeline provenance labels, snapshot caveat, and zero EBITDA synthesis on P&L waterfall."""
    sm = get_session_manager()

    if os.getenv("YUKTI_LIVE_BQ") == "1":
        monkeypatch.delenv("YUKTI_FORCE_BQ_FAIL", raising=False)
        st1 = sm.get_or_create(f"p110a-f01-{time.time_ns()}", persona="CMD", language="en")
        r_f01 = asyncio.run(
            run_planner_turn(
                "What was revenue from operations in FY24?",
                st1,
                "CMD",
                "turn-f01",
                "en",
                time.perf_counter(),
                spec_override=QuerySpec(domain="finance", metric="corporate_revenue_cr", period=Period(fy="FY24")),
            )
        )
        assert r_f01 is not None
        c_f01 = r_f01["contract"]
        assert c_f01["provenance"]["label"] == "verified_ar"
        assert c_f01["provenance"]["doc"] == "IOCL_AR_FY2023-24.pdf"
        assert str(c_f01["provenance"]["page_label"]) == "109"
        assert all("unverified" not in str(s).lower() for s in c_f01["sources"])

        st2 = sm.get_or_create(f"p110a-f15-{time.time_ns()}", persona="DIR_FIN", language="en")
        r_f15 = asyncio.run(
            run_planner_turn(
                "What was ROCE in FY23?",
                st2,
                "DIR_FIN",
                "turn-f15",
                "en",
                time.perf_counter(),
                spec_override=QuerySpec(domain="finance", metric="roce_pct", period=Period(fy="FY23")),
            )
        )
        assert r_f15 is not None
        c_f15 = r_f15["contract"]
        assert c_f15["provenance"]["label"] == "verified_ar"
        assert c_f15["provenance"]["badge"] == "AR-printed"

    monkeypatch.setenv("YUKTI_FORCE_BQ_FAIL", "1")
    st3 = sm.get_or_create(f"p110a-snap-{time.time_ns()}", persona="CMD", language="en")
    r_snap = asyncio.run(
        run_planner_turn(
            "What was IOCL's PAT in FY24?",
            st3,
            "CMD",
            "turn-snap",
            "en",
            time.perf_counter(),
            spec_override=QuerySpec(domain="finance", metric="pat_cr", period=Period(fy="FY24")),
        )
    )
    assert r_snap is not None
    c_snap = r_snap["contract"]
    assert c_snap["status"]["source"] == "local_snapshot"
    assert c_snap["generated_sql"] is None
    assert c_snap["provenance"]["label"] == "local_snapshot"
    assert "Served from the verified local snapshot of " in c_snap["caveat"]
    assert "BigQuery unavailable." in c_snap["caveat"]
    assert c_snap["sources"][0]["object"].startswith("local_snapshot:fact_financial_statement_line@")

    comp = Compiler()
    spec_pnl = QuerySpec(metric="pnl_statement", period=Period(fy="FY26"))
    compiled_pnl = comp.compile(spec_pnl)
    res_pnl = asyncio.run(comp.execute(compiled_pnl))
    vis = build_visual(spec_pnl, compiled_pnl, res_pnl.columns, res_pnl.rows, "waterfall", "P&L", "FY26", "replace", len(res_pnl.rows))
    wf_stages = [str(r.get("pnl_stage", "")) for r in vis["chart"]["data"]]
    assert all("EBITDA" not in st.upper() for st in wf_stages), f"Found synthesized EBITDA in waterfall stages: {wf_stages}"
    for kpi in vis["kpis"]:
        assert "EBITDA" not in str(kpi.get("label", "")).upper()
