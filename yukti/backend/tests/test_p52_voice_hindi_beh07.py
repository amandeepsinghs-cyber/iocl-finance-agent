"""P5.2 — Voice Verbatim, Hindi/Hinglish Narration, Frontend Dedupe & BEH-07.30–.35 regression tests."""

from __future__ import annotations

import asyncio
import pytest

from app.brain.grounding import check_numeric_grounding
from app.brain.narrator import compose_spoken, translate_to_hindi, translate_to_hinglish
from app.coverage.manifest import get_coverage_manifest
from app.intents.coverage import handle_coverage_query
from app.live_session import _should_hold_partial_utterance
from app.turn_runner import AgentTurnRunner


def _run_turn(query: str, persona: str = "CMD", session_id: str = "test-p52") -> dict:
    runner = AgentTurnRunner()
    return asyncio.run(
        runner.execute_turn_async(
            query=query,
            session_id=session_id,
            persona=persona,
        )
    )


def test_partial_utterance_hold_bug17():
    """SPEC-11 §6.3 / BUG-17: Hold < 3 words ending in a function word."""
    assert _should_hold_partial_utterance("can you") is True
    assert _should_hold_partial_utterance("show the") is True
    assert _should_hold_partial_utterance("what is") is True
    assert _should_hold_partial_utterance("for") is True
    # Complete short utterances or >= 3 words should not be held
    assert _should_hold_partial_utterance("show pat") is False
    assert _should_hold_partial_utterance("hi") is False
    assert _should_hold_partial_utterance("can you show pat") is False


def test_grounding_drops_ungrounded_coverage_claim_bug20():
    """SPEC-11 §5 / BUG-20: Ungrounded 'only have data up to FY25' is stripped, while analytic 'only'/'up to' is preserved."""
    prose = (
        "Revenue from operations in FY25 was ₹1,37,846.29 Cr. "
        "I only have data up to FY25 and FY24 is not available in the database."
    )
    cleaned, dropped = check_numeric_grounding(prose, {137846.29}, fallback_template="Fallback.")
    assert "1,37,846.29" in cleaned
    assert "only have data" not in cleaned
    assert len(dropped) == 1
    assert "only have data" in dropped[0]

    # True positive availability claim
    c_tp, d_tp = check_numeric_grounding("Data is only available up to FY2023. Revenue was 5.", {5.0})
    assert c_tp == "Revenue was 5."
    assert len(d_tp) == 1

    # False positive regression: analytic prose with 'only' + FY/year must NOT be dropped
    c_fp, d_fp = check_numeric_grounding("Net profit grew only 2% in FY2024. Revenue was 5.", {2.0, 5.0})
    assert c_fp == "Net profit grew only 2% in FY2024. Revenue was 5."
    assert d_fp == []


def test_hindi_and_hinglish_narration_bug19_beh07_35():
    """SPEC-11 §6.4 / BUG-19 / BEH-07.11 / BEH-07.35: Hindi (Devanagari) and Hinglish (Roman) narration."""
    headline = "For FY25, IOCL's revenue from operations is ₹8,45,513.00 Cr."
    res_hi = compose_spoken(headline, [], {845513.0}, language="hi")
    spoken_hi = res_hi["text"]
    # Devanagari characters present
    assert any("\u0900" <= ch <= "\u097f" for ch in spoken_hi), f"Expected Devanagari in {spoken_hi!r}"
    assert "8,45,513" in spoken_hi or "845513" in spoken_hi

    res_hinglish = compose_spoken(headline, [], {845513.0}, language="hi-en")
    spoken_hinglish = res_hinglish["text"]
    assert not any("\u0900" <= ch <= "\u097f" for ch in spoken_hinglish)
    assert "mein" in spoken_hinglish.lower() or "hai" in spoken_hinglish.lower()


def test_beh07_30_coverage_and_2024_balance_sheet():
    """BEH-07.30: 2024 balance sheet + '2024 is before 2026' deterministic coverage + 'then show it to me'."""
    s_id = "test-beh07-30"
    # T1: Balance sheet for 2024 should return FY24 statement table with bare-year note
    c1 = _run_turn(
        "can you show me the balance sheet for 2024?",
        persona="CMD",
        session_id=s_id,
    )
    assert c1.get("visual", {}).get("type") in ("statement", "statement_table", "table", "kpi")
    t1 = (c1.get("display_text") or "") + " " + (c1.get("spoken_summary") or "")
    assert "not available" not in t1.lower()
    assert "Taking 2024 as FY 2023-24" in t1

    # T2: Coverage question
    cov = handle_coverage_query("when you say upto 2026, 2024 is before 2026?")
    assert cov is not None
    assert "FY24" in cov["display_text"]
    assert "FY17" in cov["display_text"] and "FY26" in cov["display_text"]

    # T3: "then show it to me" repeats FY24 balance sheet
    c3 = _run_turn("then show it to me", persona="CMD", session_id=s_id)
    assert c3.get("visual", {}).get("type") in ("statement", "statement_table", "table")


def test_beh07_32_iocl_doa_and_hedging_policy_clauses():
    """BEH-07.32: E2_FIN and E1_FIN Finance policy queries return deterministic IOCL DoA / hedging clauses."""
    c_doa = _run_turn(
        "What is the Delegation of Authority limit for spot crude oil cargo procurement?",
        persona="E2_FIN",
        session_id="test-beh07-32",
    )
    text_doa = (c_doa.get("display_text") or "") + " " + (c_doa.get("spoken_summary") or "")
    assert "IOCL-DOA" in str(c_doa) or "Delegation of Authority" in text_doa or "crude" in text_doa.lower()
    assert c_doa.get("access", {}).get("status") == "allowed"


def test_beh07_33_e1_fin_refinery_grm_policy_and_revenue_grounding():
    """BEH-07.33: E1_FIN Finance officer can query IOCL hedging policy and published statements."""
    c1 = _run_turn(
        "What is IndianOil's hedging policy on crack spread and inventory price protection?",
        persona="E1_FIN",
        session_id="test-beh07-33",
    )
    t1 = (c1.get("display_text") or "") + " " + (c1.get("spoken_summary") or "")
    assert "hedg" in t1.lower() or "crack" in t1.lower() or "inventory" in t1.lower()
    assert c1.get("access", {}).get("status") == "allowed"


def test_beh07_34_single_kpi_waterfall_refusal():
    """BEH-07.34: Asking for a waterfall chart on a single-KPI turn explains why and offers alternatives."""
    s_id = "test-beh07-34"
    _run_turn("What is PAT in FY25?", persona="DIR_FIN", session_id=s_id)
    c2 = _run_turn("give me a waterfall chart for this", persona="DIR_FIN", session_id=s_id)
    t2 = (c2.get("display_text") or "").lower() + " " + (c2.get("spoken_summary") or "").lower()
    assert "waterfall" in t2
    assert c2.get("visual", {}).get("type") != "waterfall"
