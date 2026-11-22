"""v12 replay of feedback/current_refinements.md (22-Nov-2026 10:57–11:08) — plan_fix.md V1–V7."""
from __future__ import annotations

import time

import pytest

from app.config import DEFAULT_TEXT_MODEL
from app.session_memory import get_session_manager
from app.turn_runner import AgentTurnRunner


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("YUKTI_FORCE_BQ_FAIL", "1")
    monkeypatch.setenv("YUKTI_CONTRACT_V3_FIELDS", "all")
    monkeypatch.setattr("app.brain.explain_screen._call_gemini_screen_explain", lambda *a, **kw: None)

    def _fake_oil(benchmark: str):
        from datetime import datetime, timedelta, timezone

        days = {}
        d0 = datetime.now(timezone.utc) - timedelta(days=5 * 366)
        for i in range(0, 5 * 366, 7):
            days[(d0 + timedelta(days=i)).strftime("%Y-%m-%d")] = 100.0 + (i % 90)
        last = max(days)
        return {
            "benchmark": benchmark, "symbol": "IOC.NS" if benchmark == "iocl" else "BZ=F", "label": "IndianOil share price (NSE:IOC)",
            "short": "IOC.NS", "unit": "₹/share", "currency": "INR",
            "live": {"price": 150.5, "change_pct": 1.83, "as_of": f"{last}T09:58:10+00:00"},
            "fy_series": [], "monthly": [], "daily": [], "history": {"days": len(days), "first": min(days), "last": last, "saved_days": len(days), "new_days": 0},
            "source": "Yahoo Finance (IOC.NS)", "fetched_at": "", "stale": False, "_days": days,
        }

    cache = {}

    def _get(b):
        cache.setdefault(b, _fake_oil(b))
        return cache[b]

    monkeypatch.setattr("app.market.oil_intent.get_oil_prices", _get)
    monkeypatch.setattr("app.market.oil_intent.get_daily_history", lambda b: _get(b)["_days"])
    yield


# ------------------------------------------------------------------ V1: stock price routing (any word order)
STOCK_QUERIES = [
    "Show me the current stock price of IndianOil.",
    "Show the historical stock market price of IndianOil for the past 5 years.",
    "Can you plot the stock market price?",
    "I am asking the stock mrket price",
    "Do me a favor and run a discounted cash flow model. First, do this. Can you show me the current stock price?",
    "Where can I see the current stock market price? For the past 5 years.",
]


def test_v1_stock_detector() -> None:
    from app.market.oil_intent import detect_stock_price_plot

    for q in STOCK_QUERIES:
        r = detect_stock_price_plot(q)
        assert r is not None and r["benchmark"] == "iocl", q
    for q in (
        "Can you run a DCF model on the current stock price? And tell me if it is undervalued or overvalued.",
        "Run the 10-year DCF valuation agent against IndianOil's live NSE:IOC share price.",
        "Overlay the share price on this chart",
        "What are the analysts saying about the share price target?",
        "Can I see the cash flow statement for the past five years?",
    ):
        assert detect_stock_price_plot(q) is None, q


@pytest.mark.asyncio
async def test_v1_stock_queries_render_yahoo_chart_not_ar() -> None:
    runner = AgentTurnRunner(model_name=DEFAULT_TEXT_MODEL)
    sid = f"v12-stock-{time.time_ns()}"
    for q in STOCK_QUERIES[:4]:
        c = await runner.execute_turn_async(q, session_id=sid, persona="CMD")
        assert c["visual"]["type"] == "chart", q
        assert c.get("provenance", {}).get("label") != "verified_ar", q
        assert "Yahoo Finance" in str(c["sources"]), q
        assert "IndianOil (NSE:IOC" in c["spoken_summary"], q


# ------------------------------------------------------------------ V2: no self-confirmation
def test_v2_long_run_sentence_is_not_consent() -> None:
    from app.intents.confirm import detect_confirm_intent

    assert detect_confirm_intent("Run the 10-year DCF valuation agent against IndianOil's live NSE:IOC share price.") is None
    for ok in ("Please go ahead.", "Yeah, please go ahead.", "run it", "Run the DCF", "Yes, please go ahead and run the full DCF model for IOCL now", "haan, chalao"):
        assert detect_confirm_intent(ok) == "confirm", ok


# ------------------------------------------------------------------ V3: FY24-25 parsing + reduction wording
def test_v3_fy24_25_reduction_explains_fy25_fall() -> None:
    from app.brain.profit_explainer import detect_profit_variance, resolve_periods

    for q in ("Why was there a reduction in net profit in FY24-25?", "Why did profit decline in 2024-25?"):
        m = detect_profit_variance(q, None)
        assert m is not None and resolve_periods(m) == ("FY24", "FY25"), q

    class _S:
        turns: list = []
        last_profit_variance = None
        last_user_query = "No, I'm asking in the financial year 2024-25. Why there was a reduction?"

    m = detect_profit_variance("And why was there a reduction in net profit?", _S())
    assert m is not None and resolve_periods(m) == ("FY24", "FY25")


# ------------------------------------------------------------------ V4: cash flow variance bridge
@pytest.mark.asyncio
async def test_v4_cash_flow_reduction_bridge() -> None:
    runner = AgentTurnRunner(model_name=DEFAULT_TEXT_MODEL)
    sid = f"v12-cfv-{time.time_ns()}"
    for q in ("why did the net cash reduce in FY24-25?", "Why was there a reduction in cash flow in FY24-25 to 33,286 crore?"):
        c = await runner.execute_turn_async(q, session_id=sid, persona="CMD")
        chart = c["visual"]["chart"]
        assert chart["kind"] == "waterfall" and "FY24" in c["visual"]["title"] and "FY25" in c["visual"]["title"], q
        assert chart["data"][0]["amount_cr"] == pytest.approx(68097, abs=1)
        assert chart["data"][-1]["amount_cr"] == pytest.approx(33286, abs=1)
        assert abs(sum(r["amount_cr"] for r in chart["data"][1:-1]) - (33286.26 - chart["data"][0]["amount_cr"])) < 1.0
        assert "33,286" in c["spoken_summary"] and "profit before tax" in c["spoken_summary"]
        assert c.get("provenance", {}).get("label") != "verified_ar"


# ------------------------------------------------------------------ V5: display length never truncated
def test_v5_profit_display_under_600() -> None:
    from app.brain.profit_explainer import answer_profit_variance, detect_profit_variance

    for q in ("Why did profit rise in FY24?", "Why was the profit low in FY25?", "Why did profit jump in FY26?", "Why did profit fall in FY23?"):
        m = detect_profit_variance(q, None)
        c = answer_profit_variance(m, None, "CMD", "t", "en", time.perf_counter(), "You're right, sir — here is the profit bridge you asked for.")
        assert len(c["display_text"]) <= 600, (q, len(c["display_text"]))
