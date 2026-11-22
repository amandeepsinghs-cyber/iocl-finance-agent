"""v11 golden-conversation replay of feedback/current_refinements.md (22-Nov-2026 09:41–09:50) — plan_fix.md R1–R11."""
from __future__ import annotations

import time
from typing import Any, Dict

import pytest

from app.agents.dcf_agent import build_dcf_model_spec
from app.config import DEFAULT_TEXT_MODEL
from app.finance.dcf.assumptions import defaults_from_ssot
from app.finance.dcf.inputs import load_ssot_snapshot_rows, load_wacc_annual_rows
from app.finance.dcf.run import run_dcf
from app.session_memory import get_session_manager
from app.turn_runner import AgentTurnRunner


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("YUKTI_FORCE_BQ_FAIL", "1")
    monkeypatch.setenv("YUKTI_CONTRACT_V3_FIELDS", "all")
    monkeypatch.setattr("app.brain.explain_screen._call_gemini_screen_explain", lambda *a, **kw: None)
    yield


def _no_codes(text: str) -> None:
    for code in ("PL.", "REV.", "LEVY.", "CF."):
        assert code not in text, f"raw line code leaked: {text}"


# ------------------------------------------------------------------ R1: profit variance explainer
def test_r1_profit_variance_detection_and_periods() -> None:
    from app.brain.profit_explainer import compute_pat_bridge, detect_profit_variance, resolve_periods

    cases = {
        "Why was the profit exceptionally low in 24? 25?": ("FY24", "FY25"),
        "Why was the profit exceptionally low in 24? 25?It was around 12,000. The baseline is mostly around 36, I see. 39.": ("FY24", "FY25"),
        "No, but which screen are you showing? I'm still seeing the previous screen of the net profit is 31,000. It is 36,802, right? And I'm asking why is it less, like why is it 12,962? What happened?": ("FY24", "FY25"),
        "Explain why the profit was twelve thousand nine hundred sixty-two crore in the previous year.": ("FY24", "FY25"),
        "Why is the profit different?": ("FY24", "FY25"),
        "Why did profit jump in FY26?": ("FY25", "FY26"),
    }
    for q, expected in cases.items():
        m = detect_profit_variance(q, None)
        assert m is not None, q
        assert resolve_periods(m) == expected, q

    for q in ("Can you show me the profit and loss statement for the past 5 years?", "Run the DCF and tell me if it is undervalued"):
        assert detect_profit_variance(q, None) is None, q

    br = compute_pat_bridge("FY24", "FY25")
    assert abs(br["residual"]) < 1.0  # bridge closes to the verified PAT
    assert br["pat_to"] == pytest.approx(12961.57, abs=0.01)
    assert br["gross_margin_impact"] < -25000


@pytest.mark.asyncio
async def test_r1_r2_transcript_profit_turns_render_waterfall_and_never_repeat() -> None:
    runner = AgentTurnRunner(model_name=DEFAULT_TEXT_MODEL)
    sid = f"v11-profit-{time.time_ns()}"

    c0 = await runner.execute_turn_async("Can you show me the profit and loss statement for the past 5 years?", session_id=sid, persona="CMD")
    assert c0["visual"]["type"] in ("statement", "table", "chart")
    assert "728,445" not in c0["spoken_summary"]  # R7 Indian grouping

    c1 = await runner.execute_turn_async("Why was the profit exceptionally low in 24? 25?", session_id=sid, persona="CMD")
    chart = c1["visual"]["chart"]
    assert c1["visual"]["type"] == "chart" and chart["kind"] == "waterfall"
    assert chart["x"] == "step" and chart["y"] == "amount_cr"
    assert chart["data"][0]["type"] == "total" and chart["data"][-1]["type"] == "total"
    assert "FY24" in c1["visual"]["title"] and "FY25" in c1["visual"]["title"]
    assert "12,962" in c1["spoken_summary"] and "GRM" in c1["spoken_summary"]
    _no_codes(c1["spoken_summary"])

    c2 = await runner.execute_turn_async("No, no, this is 31, right? I'm talking about why is it different in the year 24-25.", session_id=sid, persona="CMD")
    assert c2["visual"]["chart"]["kind"] == "waterfall"
    assert c2["spoken_summary"] != c1["spoken_summary"]  # never repeat verbatim

    c3 = await runner.execute_turn_async(
        "No, but which screen are you showing? I'm still seeing the previous screen of the net profit is 31,000. "
        "It is 36,802, right? And I'm asking why is it less, like why is it 12,962? What happened?",
        session_id=sid, persona="CMD",
    )
    assert c3.get("provenance", {}).get("label") != "verified_ar"
    assert "FY25" in c3["visual"]["title"]
    assert c3["spoken_summary"].startswith("You're right, sir")

    c4 = await runner.execute_turn_async("Okay, I think the screen is not doing any justification to what is going on.", session_id=sid, persona="CMD")
    assert c4.get("provenance", {}).get("label") != "verified_ar"
    assert "Ind AS" not in c4["spoken_summary"]


# ------------------------------------------------------------------ R4: 10-year cash flow trend
@pytest.mark.asyncio
async def test_r4_total_cash_flow_ten_years() -> None:
    runner = AgentTurnRunner(model_name=DEFAULT_TEXT_MODEL)
    sid = f"v11-cf-{time.time_ns()}"
    c = await runner.execute_turn_async("So can you show me the total? Show me the total cash flow. For the past 10 years.", session_id=sid, persona="CMD")
    assert c["visual"]["type"] == "chart"
    data = c["visual"]["chart"]["data"]
    assert len(data) == 10 and data[0]["fiscal_year"] == "FY17" and data[-1]["fiscal_year"] == "FY26"
    assert data[-1]["free_cash_flow_cr"] == pytest.approx(44977.48, abs=0.05)
    assert c.get("provenance", {}).get("label") != "verified_ar"
    assert "continuous" not in c["spoken_summary"].lower() and "not available" not in c["spoken_summary"].lower()

    c5 = await runner.execute_turn_async("Okay, give me for the past 5 years at least. I want to see the cash flow trend for the past 5 years.", session_id=sid, persona="CMD")
    assert len(c5["visual"]["chart"]["data"]) == 5


# ------------------------------------------------------------------ R3: "VAT" misheard WACC after DCF
@pytest.mark.asyncio
async def test_r3_vat_misheard_as_wacc_reruns_dcf() -> None:
    assump = defaults_from_ssot(load_ssot_snapshot_rows(), load_wacc_annual_rows(), "2026-03-31")
    spec = build_dcf_model_spec(run_dcf(assump), assump)
    sid = f"v11-vat-{time.time_ns()}"
    sess = get_session_manager().get_or_create(sid, persona="CMD", language="en")
    sess.turns.append({"turn_id": "t-dcf", "visual": {"type": "dcf_model", "dcf_model": spec}, "spoken_summary": "DCF ready."})
    sess.last_agent_result = {"agent": "dcf_agent", "inputs": {}}

    from app.finance.dcf.followup import detect_dcf_followup

    req = detect_dcf_followup("Can you take the VAT to be 10 instead of 9.25?", sess)
    assert req is not None and req["intent"] == "whatif" and req["overrides"] == {"wacc_pct": 10.0}

    runner = AgentTurnRunner(model_name=DEFAULT_TEXT_MODEL)
    c = await runner.execute_turn_async("Can you take the VAT to be 10 instead of 9.25?", session_id=sid, persona="CMD")
    assert c["visual"]["type"] == "dcf_model"
    assert c["visual"]["dcf_model"]["wacc_build"]["wacc_pct"] == pytest.approx(10.0, abs=0.01)


# ------------------------------------------------------------------ R5/R7/R8 helpers
def test_r5_spoken_strips_citations_and_caps_length() -> None:
    from app.knowledge.ar_deep_qa import make_spoken

    txt = ("The Profit After Tax for 2024-25 was ₹12,962 Crore [AR FY26 p.99]. Revenue was ₹8,45,513 Crore [AR FY26 p.172]. "
           "Lower profitability reflects suppressed marketing margins [AR FY26 p.37]. Extra sentence.")
    s = make_spoken(txt)
    assert "[AR" not in s and s.count(".") <= 3


def test_r7_indian_grouping() -> None:
    from app.brain.inr_format import fmt_inr_cr
    from app.brain.presenter import fmt_num

    assert fmt_inr_cr(728445.4) == "₹7,28,445 crore"
    assert fmt_num(886224.41, "inr_cr") == "₹8,86,224 crore"
    assert fmt_inr_cr(-36461.9, signed=True) == "−₹36,462 crore"
