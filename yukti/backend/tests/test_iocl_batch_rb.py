"""Batch R-B regression tests covering Task 0, Step R4 (IOCL-R04), and Step R5 (IOCL-R06 to R10)."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

from app.agents.dcf_agent import build_dcf_model_spec
from app.config import DEFAULT_TEXT_MODEL
from app.finance.dcf import followup as dcf_followup
from app.finance.dcf.assumptions import defaults_from_ssot
from app.finance.dcf.inputs import load_ssot_snapshot_rows, load_wacc_annual_rows
from app.finance.dcf.run import run_dcf
from app.knowledge import ar_deep_qa
from app.session_memory import get_session_manager
from app.tools.policy_search import PolicySearchEngine
from app.turn_runner import AgentTurnRunner


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Task 0 & IOCL-R06: Warmup cache reset, verbatim FY26 DCF SSOT, zero E&P copy
# ---------------------------------------------------------------------------
def test_task0_warmup_cache_purged_and_dcf_ssot_base() -> None:
    cache_path = _repo_root() / "yukti" / "backend" / "certified" / "answer_cache_warmup.json"
    assert json.loads(cache_path.read_text(encoding="utf-8")) == {}

    assump = defaults_from_ssot(load_ssot_snapshot_rows(), load_wacc_annual_rows(), "2026-03-31")
    assert assump.shares_outstanding.value == pytest.approx(1412.1238, abs=0.001)
    assert assump.borrowings_inr_cr.value == pytest.approx(110668.22, abs=0.05)
    assert assump.lease_liab_inr_cr.value == pytest.approx(11934.38, abs=0.05)
    assert assump.market_price_inr.value == pytest.approx(135.4, abs=0.05)
    assert assump.wacc_pct.value == pytest.approx(9.2534, abs=0.01)

    res = run_dcf(assump)
    spec = build_dcf_model_spec(res, assump)
    assert spec["per_share"]["intrinsic_inr"] == pytest.approx(265.26, abs=0.5)
    assert spec["forecast"]["years"][0] == "FY27"
    assert spec["forecast"]["lines"]["revenue"][0] == pytest.approx(799841.03, abs=1.0)
    assert spec["forecast"]["lines"]["discount_factor"][0] == pytest.approx(0.9153, abs=0.001)

    # IOCL-R06: Zero E&P copy in tornado driver labels and zero "JSON" leak in explain prompt
    joined_labels = " ".join(lbl for tup in dcf_followup.DRIVER_LABELS.values() for lbl in tup).lower()
    for banned in ("boe", "production trend", "hpcl", "ovl"):
        assert banned not in joined_labels
    assert "refining & marketing" in joined_labels
    assert "cpcl" in joined_labels
    assert "based on the json" not in dcf_followup._EXPLAIN_SYS.lower()
    assert "model summary below" in dcf_followup._EXPLAIN_SYS.lower()


# ---------------------------------------------------------------------------
# Step R4 (IOCL-R04): PolicySearch paths/BQ AR + Universal AR Deep-QA Route
# ---------------------------------------------------------------------------
def test_step_r4_policy_search_paths_and_ar_retriever_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YUKTI_FORCE_BQ_FAIL", "1")
    eng = PolicySearchEngine()
    loaded = eng._load_local_csv()
    # Verifies fixed _roots loaded both 8,437 AR chunks and 138 financial_notes_corpus rows
    assert len(loaded) >= 8500

    local_hit = eng.search("delegation of powers capital expenditure", top_k=3)
    assert local_hit["status"] == "success"
    assert len(local_hit["clauses"]) >= 1

    # Mock ARRetriever for BQ AR fallback helper
    class _StubARRetriever:
        def retrieve(self, query: str, fiscal_year: str | None = None, top_k: int = 4) -> List[Dict[str, Any]]:
            return [{
                "chunk_id": "AR_FY26_P319_C01",
                "fiscal_year": "FY26",
                "source_doc": "IOCL_AR_FY2025-26.pdf",
                "source_page": 319,
                "source_page_label": "319",
                "section": "Notes to Consolidated Financial Statements",
                "note_no": "Note 36",
                "heading": "Contingent Liabilities & Commitments",
                "citation": "[AR FY26 p.319]",
                "text": "Claims against the Company not acknowledged as debts stood at ₹12,450 crore.",
                "score": 0.91,
            }]

    monkeypatch.setattr("app.knowledge.ar_retriever.ARRetriever", lambda: _StubARRetriever())
    bq_clauses = eng._search_bq_ar_and_notes("contingent liabilities", top_k=3)
    assert len(bq_clauses) >= 1
    assert any("[AR FY26 p.319]" in str(c.get("clause_ref", "")) and "IOCL_AR_FY2025-26" in str(c.get("doc_id", "")) and c.get("provenance") == "real" for c in bq_clauses)


def test_step_r4_ar_deep_qa_detectors_and_mocked_vertex_bq() -> None:
    assert ar_deep_qa.detect_ar_deep_qa("What are IOCL's contingent liabilities disclosed in the FY26 Annual Report?") is not None
    assert ar_deep_qa.detect_ar_deep_qa("Tell me about Panipat P-25 expansion and Net-Zero 2046 target") is not None
    assert ar_deep_qa.detect_ar_deep_qa("Show IOCL's P&L statement for FY26") is None
    assert ar_deep_qa.should_fallback_to_ar("Hello") is False
    assert ar_deep_qa.should_fallback_to_ar("What did IndianOil highlight about petchem integration?") is True

    class _StubAR:
        def retrieve(self, query: str, fiscal_year: str | None = None, top_k: int = 8) -> List[Dict[str, Any]]:
            return [{
                "chunk_id": "AR_FY26_P319_C01",
                "fiscal_year": "FY26",
                "source_doc": "IOCL_AR_FY2025-26.pdf",
                "source_page": 319,
                "source_page_label": "319",
                "section": "Notes to Standalone Financial Statements",
                "note_no": "Note 36",
                "heading": "Contingent Liabilities",
                "citation": "[AR FY26 p.319]",
                "text": "Contingent liabilities relating to tax disputes and claims totalled ₹14,820 crore as on 31 March 2026.",
            }]

    out = ar_deep_qa.answer_ar_deep_qa(
        "What are IOCL's contingent liabilities in FY26?",
        "CMD",
        "turn-ar-mock",
        "en",
        time.perf_counter(),
        retriever=_StubAR(),
        synth_fn=lambda q, chunks, lang: "Per IOCL [AR FY26 p.319], Note 36 reports ₹14,820 crore in contingent liabilities across tax disputes and pending claims.",
    )
    assert out is not None
    assert out["provenance"]["label"] == "verified_ar"
    assert "[AR FY26 p.319]" in out["display_text"]
    assert "[AR" not in out["spoken_summary"]  # R5: citations shown on screen, not read aloud
    assert out["visual"]["type"] == "table"
    assert len(out["sources"]) >= 1


@pytest.mark.asyncio
async def test_step_r4_turn_runner_direct_and_fallback_ar_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YUKTI_FORCE_BQ_FAIL", "1")
    runner = AgentTurnRunner(model_name=DEFAULT_TEXT_MODEL)

    # Direct trigger over real local 8,437-chunk AR corpus
    c1 = await runner.execute_turn_async(
        "What are IOCL's contingent liabilities disclosed in the FY26 Annual Report?",
        session_id=f"rb-ar1-{time.time_ns()}",
        persona="CMD",
    )
    assert c1["access"]["status"] == "allowed"
    assert c1["provenance"]["label"] == "verified_ar"
    assert c1["visual"]["type"] == "table"
    assert "[AR FY26" in c1["display_text"]
    assert "[AR" not in c1["spoken_summary"]
    assert "could not fetch" not in c1["spoken_summary"].lower()

    # Fallback trigger before smalltalk when planner returns no patch
    async def _no_planner(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr("app.turn_runner.run_planner_turn", _no_planner)
    c2 = await runner.execute_turn_async(
        "How does IndianOil describe Panipat refinery expansion and net-zero 2046 roadmap?",
        session_id=f"rb-ar2-{time.time_ns()}",
        persona="CMD",
    )
    assert c2["access"]["status"] == "allowed"
    assert c2["provenance"]["label"] == "verified_ar"
    assert c2["visual"]["type"] == "table"
    assert "[AR FY" in c2["display_text"]


# ---------------------------------------------------------------------------
# Step R5 (IOCL-R07 to R10): 7-Turn User DCF Replay + Online Analyst Search Mock
# ---------------------------------------------------------------------------
def test_step_r5_analyst_consensus_online_search_mock() -> None:
    assump = defaults_from_ssot(load_ssot_snapshot_rows(), load_wacc_annual_rows(), "2026-03-31")
    spec = build_dcf_model_spec(run_dcf(assump), assump)
    dcf_facts = dcf_followup.facts_from_visual(spec)

    out = dcf_followup.answer_analyst_consensus(
        "And what does the analyst are saying? If you go online and check.",
        dcf_facts,
        "turn-analyst",
        "CMD",
        "en",
        time.perf_counter(),
        search_fn=lambda q, ctx: {
            "live_search": True,
            "summary": "Brokerage consensus across 32 analysts carries a Hold/Buy mix with mean 12M target ₹162.50 vs current ₹135.40, citing refining GRM recovery.",
            "target_inr": 162.5,
            "web_sources": [{"kind": "web", "object": "https://example.com/iocl-consensus", "title": "Brokerage Consensus"}],
            "search_queries": ["IndianOil IOC NSE analyst target price consensus"],
        },
    )
    assert out["visual"]["type"] == "chart"
    assert "162.50" in out["spoken_summary"]
    assert "JSON" not in out["spoken_summary"]
    assert any(s.get("kind") == "web" for s in out.get("sources", []))
    assert len(out["visual"]["chart"]["data"]) == 3


@pytest.mark.asyncio
async def test_step_r5_exact_7_turn_dcf_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YUKTI_FORCE_BQ_FAIL", "1")
    monkeypatch.setenv("YUKTI_CONTRACT_V3_FIELDS", "all")

    assump = defaults_from_ssot(load_ssot_snapshot_rows(), load_wacc_annual_rows(), "2026-03-31")
    base_spec = build_dcf_model_spec(run_dcf(assump), assump)

    sid = f"rb-7turn-{time.time_ns()}"
    sm = get_session_manager()
    sess = sm.get_or_create(sid, persona="CMD", language="en")
    # Turn 1: Base DCF Valuation Result seeded as completed DCF turn
    sess.turns.append({
        "turn_id": "turn-1-dcf",
        "query": "Run a 10-year DCF valuation for IOCL",
        "visual": {"type": "dcf_model", "dcf_model": base_spec},
        "dcf": base_spec,
        "spoken_summary": f"DCF intrinsic value is ₹{base_spec['per_share']['intrinsic_inr']:.2f}/share.",
    })
    sess.last_agent_result = base_spec

    runner = AgentTurnRunner(model_name=DEFAULT_TEXT_MODEL)

    # Turn 2: Analyst consensus follow-up (offline fallback, zero JSON leak)
    t2 = await runner.execute_turn_async(
        "And what does the analyst are saying? If you go online and check.",
        session_id=sid,
        persona="CMD",
    )
    assert t2["visual"]["type"] == "chart"
    assert "JSON" not in t2["spoken_summary"]
    assert "json" not in t2["spoken_summary"].lower()

    # Turn 3: WACC override re-run (IOCL-R08)
    t3 = await runner.execute_turn_async(
        "can you change the WACC to be 10.25 instead of 9.25 and run the analysis again?",
        session_id=sid,
        persona="CMD",
    )
    assert t3["visual"]["type"] == "dcf_model"
    dm3 = t3["visual"]["dcf_model"]
    assert dm3["wacc_build"]["wacc_pct"] == pytest.approx(10.25, abs=0.01)
    assert dm3["per_share"]["intrinsic_inr"] < base_spec["per_share"]["intrinsic_inr"]
    assert dm3["per_share"]["intrinsic_inr"] == pytest.approx(218.12, abs=0.5)
    assert dm3["forecast"]["lines"]["discount_factor"][0] == pytest.approx(1.0 / 1.1025, abs=0.0005)
    assert sess.last_dcf_prev is not None

    # Turn 4: "did you actually run the analysis?" -> Re-Run Proof Table (IOCL-R08)
    t4 = await runner.execute_turn_async(
        "did you actually run the analysis?",
        session_id=sid,
        persona="CMD",
    )
    assert t4["visual"]["type"] == "table"
    rows4 = {r["metric"]: r for r in t4["visual"]["table"]["rows"]}
    assert "WACC (%)" in rows4
    assert rows4["WACC (%)"]["previous_run"] == pytest.approx(9.2534, abs=0.01)
    assert rows4["WACC (%)"]["updated_run"] == pytest.approx(10.25, abs=0.01)
    assert rows4["FY27 Discount Factor (×)"]["updated_run"] == pytest.approx(0.907, abs=0.001)
    assert rows4["Intrinsic Value (₹/share)"]["updated_run"] < rows4["Intrinsic Value (₹/share)"]["previous_run"]

    # Turn 5: Growth audit comparison FY18..FY36 + plot (IOCL-R09)
    t5 = await runner.execute_turn_async(
        "can you tell me the growth rate you have assumed? from 2027 onwards? in revenue operating profit and FCF? and does it match historical trend? give me a plot",
        session_id=sid,
        persona="CMD",
    )
    assert t5["visual"]["type"] == "chart"
    data5 = t5["visual"]["chart"]["data"]
    assert len(data5) == 19
    assert data5[0]["fiscal_year"] == "FY18"
    assert data5[-1]["fiscal_year"] == "FY36"
    assert "revenue_growth_pct" in data5[0] and "ebit_growth_pct" in data5[0] and "fcff_growth_pct" in data5[0]
    assert "2.00%" in t5["spoken_summary"]

    # Turn 6: Short clarification follow-up ("I asked growth rate") -> routes to growth_audit (IOCL-R09)
    t6 = await runner.execute_turn_async(
        "I asked growth rate",
        session_id=sid,
        persona="CMD",
    )
    assert t6["visual"]["type"] == "chart"
    assert "revenue_growth_pct" in t6["visual"]["chart"]["data"][0]

    # Turn 7: Extend plot to 2036 -> continuous FY17–FY36 chart (IOCL-R10, never hijacked by what_if)
    t7 = await runner.execute_turn_async(
        "and now extend this plot to 2036",
        session_id=sid,
        persona="CMD",
    )
    assert t7["visual"]["type"] == "chart"
    data7 = t7["visual"]["chart"]["data"]
    assert len(data7) == 20
    assert data7[0]["fiscal_year"] == "FY17"
    assert data7[9]["fiscal_year"] == "FY26"
    assert data7[10]["fiscal_year"] == "FY27"
    assert data7[-1]["fiscal_year"] == "FY36"
    assert data7[0]["actual_inr_cr"] is not None
    assert data7[-1]["forecast_inr_cr"] is not None


# ---------------------------------------------------------------------------
# v10 Refinements: Live Yahoo Finance DCF, "Please go ahead", Screen Explain, P&L Order
# ---------------------------------------------------------------------------
def test_v10_live_yahoo_finance_dcf_proposal_and_valuation(monkeypatch: pytest.MonkeyPatch) -> None:
    import math
    from app.agents.dcf_agent import build_dcf_assumptions_from_inputs
    from app.agents.dcf_contract import build_dcf_proposal

    monkeypatch.setenv("YUKTI_TEST_LIVE_MARKET", "1")

    def _fake_oil_prices(benchmark: str) -> Dict[str, Any]:
        if benchmark == "iocl":
            return {
                "benchmark": "iocl",
                "symbol": "IOC.NS",
                "live": {"price": 150.50, "change_pct": 1.83, "as_of": "2026-11-20T09:58:10+00:00"},
                "history": {"last": "2026-11-20"},
                "stale": False,
            }
        if benchmark == "brent":
            return {"benchmark": "brent", "symbol": "BZ=F", "live": {"price": 89.95, "change_pct": 0.57, "as_of": "2026-11-20T21:00:00+00:00"}, "stale": False}
        return {"benchmark": "inr", "symbol": "INR=X", "live": {"price": 92.67, "change_pct": -0.65, "as_of": "2026-11-22T03:00:00+00:00"}, "stale": False}

    monkeypatch.setattr("app.market.oil_prices.get_oil_prices", _fake_oil_prices)

    prop = build_dcf_proposal("CMD", session=None)
    pa = prop["proposed_action"]
    assert pa is not None
    assert pa["inputs"]["market_price_inr"] == pytest.approx(150.50)
    assert "Yahoo Finance API" in pa["summary"]
    assert "150.50" in pa["summary"]
    assert any(i["key"] == "market_price_inr" and i["value"] == pytest.approx(150.50) for i in pa["editable_inputs"])

    asm = build_dcf_assumptions_from_inputs("job_live_test", pa["inputs"])
    res = run_dcf(asm)
    assert res["per_share"]["market_inr"] == pytest.approx(150.50)
    assert res["per_share"]["market_date"] == "2026-11-20"
    expected_up = (res["per_share"]["intrinsic_inr"] - 150.50) / 150.50 * 100
    assert res["per_share"]["upside_pct"] == pytest.approx(expected_up, abs=0.05)

    # Zero -0.00 anywhere in DCF bridge
    for item in res["bridge"]:
        val = float(item["value_inr_cr"])
        if val == 0.0:
            assert math.copysign(1.0, val) > 0


@pytest.mark.asyncio
async def test_v10_please_go_ahead_confirms_pending_dcf() -> None:
    from app.intents.confirm import detect_confirm_intent, resolve_pending_proposal_async
    from app.jobs.executor import get_executor
    from app.jobs.store import get_job_store, reset_store_for_tests

    reset_store_for_tests()
    executor = get_executor()
    executor.store = get_job_store()
    executor.step_delay_sec = 0.005

    for phrase in ("Please go ahead.", "Kindly proceed.", "Yes, please go ahead!", "Sure, run the DCF"):
        assert detect_confirm_intent(phrase) == "confirm", f"Failed on: {phrase}"

    sid = f"v10-confirm-{time.time_ns()}"
    sess = get_session_manager().get_or_create(sid, persona="CMD", language="en")
    sess.pending_actions["pa_test10"] = {
        "id": "pa_test10",
        "agent": "dcf_agent",
        "inputs": {"wacc_pct": 9.2534, "market_price_inr": 150.50},
        "editable_inputs": [],
    }

    resolved = await resolve_pending_proposal_async("Please go ahead.", sess)
    assert resolved is not None
    assert resolved["action"] == "confirm"
    assert resolved["job"]["agent"] == "dcf_agent"
    assert "pa_test10" not in sess.pending_actions


@pytest.mark.asyncio
async def test_v10_explain_on_screen_and_brent_correlation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YUKTI_FORCE_BQ_FAIL", "1")
    # Force deterministic fallback in offline test so test runs instantaneously and deterministically
    monkeypatch.setattr("app.brain.explain_screen._call_gemini_screen_explain", lambda *a, **kw: None)

    sid = f"v10-screen-{time.time_ns()}"
    sess = get_session_manager().get_or_create(sid, persona="CMD", language="en")
    sess.active_overlay = "brent"
    sess.turns.append({
        "turn_id": "turn-rev-5y",
        "user_query": "Can I see the revenue trend for the past 5 years?",
        "spoken_summary": "Gross revenue from operations moved from ₹728,445.4 crore in FY22 to ₹886,224.41 crore in FY26.",
        "visual": {
            "type": "chart",
            "title": "Gross revenue from operations (₹ cr), FY22 – FY26",
            "chart": {
                "kind": "bar",
                "x": "fiscal_year",
                "y": "gross_revenue_cr",
                "data": [
                    {"fiscal_year": "FY22", "gross_revenue_cr": 728445.40},
                    {"fiscal_year": "FY23", "gross_revenue_cr": 934952.71},
                    {"fiscal_year": "FY24", "gross_revenue_cr": 866345.36},
                    {"fiscal_year": "FY25", "gross_revenue_cr": 845513.21},
                    {"fiscal_year": "FY26", "gross_revenue_cr": 886224.41},
                ],
            },
        },
        "sources": [{"kind": "data", "object": "hrfin_gold.v_fin_trend_latest"}],
    })

    runner = AgentTurnRunner(model_name=DEFAULT_TEXT_MODEL)

    # 1. Correlation question
    q1 = "It seems there is no correlation from the Brent price to IOCL. Is it the case because of the Brent price decreases? The revenue should have increased."
    c1 = await runner.execute_turn_async(q1, session_id=sid, persona="CMD")
    assert c1["visual"]["type"] == "none"
    assert "105.1 MMT" in c1["spoken_summary"]
    assert "details are on screen" not in c1["spoken_summary"].lower()

    # 2. Explain screen walkthrough
    q2 = "Can you please explain what is going on on the screen?"
    c2 = await runner.execute_turn_async(q2, session_id=sid, persona="CMD")
    assert c2["visual"]["type"] == "none"
    assert "left axis" in c2["spoken_summary"].lower()
    assert "brent" in c2["spoken_summary"].lower()

    # 3. "What is the point you're trying to make?"
    q3 = "But what is the point you're trying to make?"
    c3 = await runner.execute_turn_async(q3, session_id=sid, persona="CMD")
    assert c3["visual"]["type"] == "none"
    assert "tailwind" in c3["spoken_summary"].lower() or "36,802" in c3["spoken_summary"]


def test_v10_pnl_total_income_anchors_income_section() -> None:
    from app.brain.statement_builder import build_statement_spec

    rows = [r for r in load_ssot_snapshot_rows("FY26", "standalone") if str(r.get("line_code", "")).startswith(("PL.", "REV.", "LEVY."))]
    spec = build_statement_spec("pnl", rows, periods=["FY26"])
    inc_sec = next(s for s in spec["sections"] if s["id"] == "income")
    codes = [r["line_code"] for r in inc_sec["rows"]]
    assert codes[-1] == "PL.TOTAL_INCOME"
    if "REV.NET_OF_EXCISE" in codes:
        assert codes.index("REV.NET_OF_EXCISE") < codes.index("PL.TOTAL_INCOME")
