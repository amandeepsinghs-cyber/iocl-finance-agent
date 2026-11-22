"""v13 replay of feedback/current_refinements.md (22-Nov-2026 11:58–12:04) — plan_fix.md W2–W9."""
from __future__ import annotations

import time

import pytest

from app.config import DEFAULT_TEXT_MODEL
from app.turn_runner import AgentTurnRunner


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("YUKTI_FORCE_BQ_FAIL", "1")
    monkeypatch.setenv("YUKTI_CONTRACT_V3_FIELDS", "all")
    monkeypatch.setattr("app.brain.explain_screen._call_gemini_screen_explain", lambda *a, **kw: None)
    fy_avg = {"FY22": 83.0, "FY23": 72.0, "FY24": 120.0, "FY25": 140.0, "FY26": 145.0}

    def _fake(benchmark: str):
        return {"benchmark": "iocl", "symbol": "IOC.NS", "live": {"price": 150.5, "change_pct": 1.8, "as_of": "2026-11-20T09:58:10+00:00"},
                "fy_series": [{"fy": k, "avg": v, "days": 240, "provisional": False} for k, v in fy_avg.items()] + [{"fy": "FY27", "avg": 150.0, "days": 150, "provisional": True}],
                "history": {"last": "2026-11-20"}, "stale": False}

    monkeypatch.setattr("app.market.oil_prices.get_oil_prices", _fake)
    yield


def test_w2_w4_detection() -> None:
    from app.brain.market_fundamentals import detect_market_vs_fundamental
    from app.market.oil_intent import detect_stock_price_plot

    q = "So the free cash flow has more than doubled. But the stock price did not double. Why?"
    m = detect_market_vs_fundamental(q, None)
    assert m is not None and m["metric"] == "fcf" and m["mode"] == "why"
    assert detect_stock_price_plot(q) is None  # never re-plot the stock chart for a "why" question

    class _S:
        turns = [{"visual": {"type": "chart", "title": "IndianOil share price (NSE:IOC), daily · 22 Nov 2021 – 22 Nov 2026"}}]

    m2 = detect_market_vs_fundamental("Can you overlay the free cash flow on top of this?", _S())
    assert m2 is not None and m2["mode"] == "overlay"
    assert detect_market_vs_fundamental("Can I see the cash flow statement for the past five years?", None) is None


@pytest.mark.asyncio
async def test_w2_why_fcf_vs_stock_answer() -> None:
    runner = AgentTurnRunner(model_name=DEFAULT_TEXT_MODEL)
    c = await runner.execute_turn_async(
        "So the free cash flow has more than doubled. But the stock price did not double. Why?", session_id=f"v13-w2-{time.time_ns()}", persona="CMD"
    )
    ch = c["visual"]["chart"]
    assert ch["kind"] == "combo" and len(ch["data"]) == 5
    assert set(ch["data"][0]) == {"fiscal_year", "free_cash_flow_cr", "ioc_share_price_avg_inr"}
    assert "negative in FY23 and FY25" in c["spoken_summary"]
    assert "times" in c["spoken_summary"]
    assert any("Yahoo Finance" in str(s.get("object")) for s in c["sources"])
    assert len(c["display_text"]) <= 600


@pytest.mark.asyncio
async def test_w3_wacc_history() -> None:
    from app.brain.market_fundamentals import detect_wacc_trend

    assert detect_wacc_trend("So can I see the WACC for the past 10 years?") is not None
    assert detect_wacc_trend("Run a re-evaluation at WACC to be 10 instead of 9.25") is None
    runner = AgentTurnRunner(model_name=DEFAULT_TEXT_MODEL)
    c = await runner.execute_turn_async("So can I see the WACC for the past 10 years?", session_id=f"v13-w3-{time.time_ns()}", persona="CMD")
    data = c["visual"]["chart"]["data"]
    assert len(data) == 10 and data[0]["fiscal_year"] == "FY17" and data[-1]["fiscal_year"] == "FY26"
    assert data[-1]["wacc_pct"] == pytest.approx(9.25, abs=0.01)
    assert c["visual"]["table"]["rows"][-1]["equity_weight_pct"] == pytest.approx(63.3, abs=0.1)


@pytest.mark.asyncio
async def test_w6_w7_fcf_only_and_concept() -> None:
    runner = AgentTurnRunner(model_name=DEFAULT_TEXT_MODEL)
    sid = f"v13-w6-{time.time_ns()}"
    c = await runner.execute_turn_async("free cash flow for the past 5 years", session_id=sid, persona="CMD")
    data = c["visual"]["chart"]["data"]
    assert set(data[0]) == {"fiscal_year", "free_cash_flow_cr"} and len(data) == 5
    assert "free cash flow" in c["spoken_summary"].lower() and "negative in FY23 and FY25" in c["spoken_summary"]

    c2 = await runner.execute_turn_async("Is this the same as free cash flow?", session_id=sid, persona="CMD")
    assert c2["spoken_summary"].startswith("No.") and "44,977" in c2["spoken_summary"] and "71,399" in c2["spoken_summary"]


@pytest.mark.asyncio
async def test_w5_consolidated_request_is_flagged() -> None:
    runner = AgentTurnRunner(model_name=DEFAULT_TEXT_MODEL)
    c = await runner.execute_turn_async("consolidated cash flow statement for the past 5 years", session_id=f"v13-w5-{time.time_ns()}", persona="CMD")
    if c["visual"].get("type") == "statement" or isinstance(c["visual"].get("statement"), dict):
        assert "aren't in the verified data" in c["spoken_summary"]
