"""Batch R-A regression tests covering Steps R1 (IOCL-R01/R05), R2 (IOCL-R03), and R3 (IOCL-R02)."""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict

import pytest

from app import config as app_config
from app.brain.bridge import bridge
from app.brain.compiler import Compiler
from app.brain.pipeline import run_planner_turn
from app.brain.presenter import build_visual
from app.brain.query_spec import Filter, Period, QuerySpec
from app.config import DEFAULT_TEXT_MODEL
from app.market import oil_intent
from app.session_memory import get_session_manager
from app.turn_runner import AgentTurnRunner


def _stmt_row(st: Dict[str, Any], line_code: str) -> Dict[str, Any]:
    for sec in st.get("sections", []):
        for row in sec.get("rows", []):
            if row.get("line_code") == line_code:
                return row
    raise AssertionError(f"Line code {line_code} not found in statement {st.get('statement')}")


# ---------------------------------------------------------------------------
# Step R1: Multi-year Statements (Years as Columns) & Clean ASR Copy
# ---------------------------------------------------------------------------
def test_step_r1_v3_field_enabled_supports_all_and_star(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YUKTI_CONTRACT_V3_FIELDS", raising=False)
    assert app_config.v3_field_enabled("statement") is False

    for token in ("all", "ALL", "*", "statement"):
        monkeypatch.setenv("YUKTI_CONTRACT_V3_FIELDS", token)
        assert app_config.v3_field_enabled("statement") is True


@pytest.mark.asyncio
async def test_step_r1_multiyear_statements_and_no_i_heard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YUKTI_CONTRACT_V3_FIELDS", "all")
    monkeypatch.setenv("YUKTI_FIN_SSOT_V3", "1")
    monkeypatch.setenv("YUKTI_FORCE_BQ_FAIL", "1")

    comp = Compiler()
    expected_periods = ["FY26", "FY25", "FY24", "FY23", "FY22", "FY21", "FY20", "FY19", "FY18", "FY17"]

    for metric, expected_stmt in (
        ("pnl_statement", "pnl"),
        ("balance_sheet", "balance_sheet"),
        ("cash_flow_statement", "cash_flow"),
    ):
        spec = QuerySpec(
            metric=metric,
            period=Period(from_="FY17", to="FY26"),
            filters=[Filter(field="scope", op="=", value="standalone")],
        )
        compiled = comp.compile(spec)
        res = await comp.execute(compiled)
        vis = build_visual(spec, compiled, res.columns, res.rows, None, metric, "", "test")
        st = vis.get("statement")
        assert st is not None, f"Missing StatementTable on {metric}"
        assert st["statement"] == expected_stmt
        assert st["periods"] == expected_periods
        if metric == "pnl_statement":
            imp = _stmt_row(st, "PL.IMPAIRMENT_FIN_ASSETS")
            assert imp["values"]["FY26"] == pytest.approx(2366.75, abs=0.01)

    ratios_spec = QuerySpec(
        metric="financial_ratios",
        period=Period(from_="FY17", to="FY26"),
        filters=[Filter(field="scope", op="=", value="standalone")],
    )
    ratios_comp = comp.compile(ratios_spec)
    ratios_res = await comp.execute(ratios_comp)
    ratios_vis = build_visual(ratios_spec, ratios_comp, ratios_res.columns, ratios_res.rows, None, "financial_ratios", "", "test")
    assert ratios_vis["type"] == "table"
    for p in expected_periods:
        assert p in ratios_vis["table"]["columns"]
    assert len(ratios_vis["table"]["rows"]) >= 8

    sm = get_session_manager()
    sess = sm.get_or_create(f"r1-asr-{time.time_ns()}", persona="CMD", language="en")
    out = await run_planner_turn(
        "What is IOCL's PAT in FY26?",
        sess,
        "CMD",
        "turn-r1-asr",
        "en",
        time.perf_counter(),
        spec_override=QuerySpec(domain="finance", metric="pat_cr", period=Period(fy="FY26")),
    )
    assert out is not None
    spoken = out["contract"]["spoken_summary"]
    assert "i heard" not in spoken.lower()
    assert "36,802" in spoken or "36802" in spoken


# ---------------------------------------------------------------------------
# Step R2: Verbatim FY17-FY26 AR Parity & FY20 Net Tax Credit Bridge
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_step_r2_verbatim_fy26_ar_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YUKTI_CONTRACT_V3_FIELDS", "all")
    monkeypatch.setenv("YUKTI_FIN_SSOT_V3", "1")
    monkeypatch.setenv("YUKTI_FORCE_BQ_FAIL", "1")

    comp = Compiler()

    pnl = await comp.execute(comp.compile(QuerySpec(metric="pnl_statement", period=Period(fy="FY26"))))
    by_pnl = {r["line_code"]: float(r["value_inr_cr"]) for r in pnl.rows}
    assert by_pnl["PL.REV_OPS"] == pytest.approx(886224.41, abs=0.01)
    assert by_pnl["PL.OTHER_INCOME"] == pytest.approx(4988.31, abs=0.01)
    assert by_pnl["PL.IMPAIRMENT_FIN_ASSETS"] == pytest.approx(2366.75, abs=0.01)
    assert by_pnl["PL.OTHER_EXP"] == pytest.approx(57600.40, abs=0.01)
    assert by_pnl["PL.DDA"] == pytest.approx(16964.82, abs=0.01)
    assert by_pnl["PL.FIN_COST"] == pytest.approx(7969.02, abs=0.01)
    assert by_pnl["PL.PBT"] == pytest.approx(48784.41, abs=0.01)
    assert by_pnl["PL.TAX"] == pytest.approx(11981.99, abs=0.01)
    assert by_pnl["PL.PAT"] == pytest.approx(36802.42, abs=0.01)
    assert by_pnl["PL.EPS_BASIC"] == pytest.approx(26.72, abs=0.01)

    bs = await comp.execute(comp.compile(QuerySpec(metric="balance_sheet", period=Period(fy="FY26"))))
    by_bs = {r["line_code"]: float(r["value_inr_cr"]) for r in bs.rows}
    assert by_bs["BS.PPE_NET"] == pytest.approx(187894.12, abs=0.01)
    assert by_bs["BS.CWIP"] == pytest.approx(82577.56, abs=0.01)
    assert by_bs["BS.INVENTORIES"] == pytest.approx(107484.12, abs=0.01)
    assert by_bs["BS.TRADE_REC_C"] == pytest.approx(14229.15, abs=0.01)
    assert by_bs["BS.CCE"] == pytest.approx(281.41, abs=0.01)
    assert by_bs["BS.TOTAL_ASSETS"] == pytest.approx(491535.12, abs=0.01)
    assert by_bs["BS.EQUITY.TOTAL"] == pytest.approx(204544.34, abs=0.01)

    cf = await comp.execute(comp.compile(QuerySpec(metric="cash_flow_statement", period=Period(fy="FY26"))))
    by_cf = {r["line_code"]: float(r["value_inr_cr"]) for r in cf.rows}
    assert by_cf["CF.CFO"] == pytest.approx(71398.57, abs=0.01)
    assert by_cf["CF.CFI"] == pytest.approx(-17661.78, abs=0.01)
    assert by_cf["CF.CFF"] == pytest.approx(-53718.55, abs=0.01)
    assert by_cf["CF.NET_CHANGE_CCE"] == pytest.approx(18.24, abs=0.01)


@pytest.mark.asyncio
async def test_step_r2_fy20_net_tax_credit_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YUKTI_CONTRACT_V3_FIELDS", "all")
    monkeypatch.setenv("YUKTI_FIN_SSOT_V3", "1")
    monkeypatch.setenv("YUKTI_FORCE_BQ_FAIL", "1")

    comp = Compiler()
    pnl20 = await comp.execute(comp.compile(QuerySpec(metric="pnl_statement", period=Period(fy="FY20"))))
    for gran in ("standard", "full"):
        res = bridge(pnl20.rows, period="FY20", granularity=gran)
        assert getattr(res, "ok", None) is True, f"FY20 {gran} bridge failed: {res}"


# ---------------------------------------------------------------------------
# Step R3: 10-Year Retail MS, HSD, LPG, ATF Prices & Delhi Tax Build-Up
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_step_r3_turn_runner_retail_fuels_and_buildup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YUKTI_FORCE_BQ_FAIL", "1")
    runner = AgentTurnRunner(model_name=DEFAULT_TEXT_MODEL)

    # 1. Exact feedback query 1: single fuel diesel in Delhi 10 years
    c1 = await runner.execute_turn_async(
        "Can you show me the diesel price in Delhi for the past 10 years?",
        session_id=f"r3-hsd-{time.time_ns()}",
        persona="CMD",
    )
    assert c1["access"]["status"] == "allowed"
    assert c1["visual"]["type"] == "chart"
    assert c1["visual"]["chart"]["kind"] == "line"
    assert len(c1["visual"]["chart"]["data"]) == 120
    assert c1["visual"]["chart"]["data"][-1]["diesel_rsp_inr_l"] == pytest.approx(87.67, abs=0.01)
    assert "87.67" in c1["spoken_summary"]

    # 2. Exact feedback query 2: dual petrol or diesel comparison 10 years
    c2 = await runner.execute_turn_async(
        "Can you show me the petrol or the diesel prices for the past 10 years?",
        session_id=f"r3-dual-{time.time_ns()}",
        persona="DIR_MKT",
    )
    assert c2["access"]["status"] == "allowed"
    assert c2["visual"]["type"] == "chart"
    assert c2["visual"]["chart"]["kind"] == "line"
    last_row = c2["visual"]["chart"]["data"][-1]
    assert last_row["petrol_rsp_inr_l"] == pytest.approx(94.77, abs=0.01)
    assert last_row["diesel_rsp_inr_l"] == pytest.approx(87.67, abs=0.01)
    assert "7.10" in c2["spoken_summary"]

    # 3. 4-Metro point-in-time comparison
    c3 = await runner.execute_turn_async(
        "What are the current petrol prices across Delhi, Mumbai, Kolkata, and Chennai?",
        session_id=f"r3-metro-{time.time_ns()}",
        persona="CMD",
    )
    assert c3["visual"]["chart"]["kind"] == "bar"
    by_city = {r["city"]: r["price"] for r in c3["visual"]["chart"]["data"]}
    assert by_city == {"Delhi": 94.77, "Mumbai": 103.44, "Kolkata": 104.95, "Chennai": 100.80}

    # 4. LPG & ATF series
    c_lpg = await runner.execute_turn_async(
        "Show Indane LPG cylinder prices in Delhi for the past 5 years",
        session_id=f"r3-lpg-{time.time_ns()}",
        persona="DIR_MKT",
    )
    assert c_lpg["visual"]["chart"]["data"][-1]["lpg_rsp_inr_cyl"] == pytest.approx(853.00, abs=0.01)

    c_atf = await runner.execute_turn_async(
        "Show ATF prices in Delhi for the past 5 years",
        session_id=f"r3-atf-{time.time_ns()}",
        persona="DIR_MKT",
    )
    assert c_atf["visual"]["chart"]["unit"] == "₹/kL"
    assert c_atf["visual"]["chart"]["data"][-1]["atf_rsp_inr_kl"] > 50000.0

    # 5. Delhi Tax Build-Up
    c_bu = await runner.execute_turn_async(
        "Break down the petrol price in Delhi — how much is base price vs central excise vs VAT?",
        session_id=f"r3-bu-{time.time_ns()}",
        persona="DIR_FIN",
    )
    assert c_bu["visual"]["chart"]["kind"] == "bar"
    comps = {r["component"]: r["amount_inr_l"] for r in c_bu["visual"]["chart"]["data"]}
    assert comps["Central Excise Duty"] == pytest.approx(19.90, abs=0.01)
    assert comps["State VAT"] == pytest.approx(15.40, abs=0.01)
    assert sum(comps.values()) == pytest.approx(94.77, abs=0.01)

    # 6. Negative guard: IOCL marketing sales volume must not be hijacked as pump price
    assert oil_intent.detect_oil_plot("Show IOCL marketing sales volume of diesel in FY26") is None


@pytest.mark.asyncio
async def test_step_r3_compiler_local_snapshot_subjects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YUKTI_FORCE_BQ_FAIL", "1")
    comp = Compiler()

    res_prices = await comp.execute(
        comp.compile(QuerySpec(metric="retail_fuel_rsp", period=Period(fy="FY26")))
    )
    assert res_prices.source == "local_snapshot"
    assert len(res_prices.rows) > 0

    res_bu = await comp.execute(
        comp.compile(QuerySpec(metric="buildup_excise_inr_l", period=Period(fy="FY26")))
    )
    assert res_bu.source == "local_snapshot"
    assert len(res_bu.rows) == 2


def test_conceptual_finance_and_conversational_ar_guards() -> None:
    from app.brain.smalltalk import detect_conceptual_finance_question
    from app.knowledge.ar_deep_qa import _is_garbled_ocr, _trim_to_sentence, should_fallback_to_ar

    # Conceptual finance questions must NOT be hijacked into FY26 P&L dump
    assert detect_conceptual_finance_question(
        "what is the difference in P&L and Income stateemnt or they are the same thing?"
    )
    assert detect_conceptual_finance_question("What is the difference between EBITDA and EBIT?")
    assert detect_conceptual_finance_question("Are standalone and consolidated financials the same thing?")
    # Real IOCL data requests must NOT be intercepted as conceptual
    assert not detect_conceptual_finance_question("Show IOCL's Schedule III Profit and Loss statement for FY26")
    assert not detect_conceptual_finance_question("Can I see the income statement for the past 5 years?")

    # Conversational filler must NOT trigger AR RAG vector search
    assert not should_fallback_to_ar("All right, I'll do one now.")
    assert not should_fallback_to_ar("Sounds good, let me try another one.")
    # Substantive IOCL/AR questions still trigger AR RAG
    assert should_fallback_to_ar("What were IOCL's contingent liabilities in the FY26 annual report?")

    # Garbled FY19 custom-font OCR detection + clean sentence-boundary trimming
    assert _is_garbled_ocr("418 Indian Oil TOKEEPYOURPASSWORDCONlDENTIAL 4HE #OMPANY OPERATES")
    assert not _is_garbled_ocr("Contingent liabilities for IndianOil stood at ₹58,642 crore in FY26.")
    assert _trim_to_sentence(
        "IndianOil adopted Ind AS 116 from April 1, 2019 across refinery and depot leases. Furthermore, the Group planned to adopt without r"
    ) == "IndianOil adopted Ind AS 116 from April 1, 2019 across refinery and depot leases."


def test_pnl_deduplicates_excise_and_places_net_revenue_under_income() -> None:
    from app.brain.statement_builder import build_statement_spec

    rows = [
        {"fiscal_year": "FY26", "line_code": "PL.REV_OPS", "line_name": "Revenue from Operations (Gross)", "value_inr_cr": 886224.41, "verified": True},
        {"fiscal_year": "FY26", "line_code": "LEVY.TOTAL", "line_name": "Excise Duty on Sale of Goods", "value_inr_cr": 102066.54, "verified": True},
        {"fiscal_year": "FY26", "line_code": "PL.EXCISE", "line_name": "Excise Duty", "value_inr_cr": 102066.54, "verified": True},
        {"fiscal_year": "FY26", "line_code": "REV.NET_OF_EXCISE", "line_name": "Revenue from Operations (Net of Excise Duty)", "value_inr_cr": 784157.87, "verified": True},
        {"fiscal_year": "FY26", "line_code": "PL.OTHER_INCOME", "line_name": "Other Income", "value_inr_cr": 4988.31, "verified": True},
        {"fiscal_year": "FY26", "line_code": "PL.TOTAL_INCOME", "line_name": "Total Income", "value_inr_cr": 891212.72, "verified": True},
    ]
    spec = build_statement_spec("pnl", rows, periods=["FY26"], fy="FY26")
    all_codes = [r["line_code"] for sec in spec["sections"] for r in sec["rows"]]
    assert "LEVY.TOTAL" in all_codes
    assert "PL.EXCISE" not in all_codes
    income_sec = next(sec for sec in spec["sections"] if sec["id"] == "income")
    assert any(r["line_code"] == "REV.NET_OF_EXCISE" for r in income_sec["rows"])
