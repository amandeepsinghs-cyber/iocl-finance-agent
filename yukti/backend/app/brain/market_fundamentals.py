"""Market vs fundamentals skill (W2/W4, plan_fix.md v13).

Answers "Free cash flow more than doubled but the stock price didn't — why?" and "overlay free cash flow on the stock
chart" with a fiscal-year combo chart (internal SSOT metric bars + external Yahoo Finance IOC.NS yearly-average price
line) and a data-grounded explanation (volatility of FCF, negative years, implied price/FCF multiple).
Also provides the 10-year WACC history (W3) from `fact_wacc_annual`.
"""
from __future__ import annotations

import math
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from app.brain.inr_format import fmt_inr_cr

SHARES_CR = 1412.1238  # IOCL AR FY26 (crore shares, post 1:2 bonus) — same as DCF engine

_STOCK_WORD_RE = re.compile(r"\b(stock|share|market\s+price|ioc\.?ns|nse\s*:?\s*ioc|valuation\s+multiple|market\s+cap\w*)\b", re.I)
_METRIC_RE = re.compile(r"\b(free\s+cash\s*flow|fcf|operating\s+cash\s*flow|ocf|cash\s*flow|profit|pat|earnings|net\s+income|ebitda)\b", re.I)
_WHY_REL_RE = re.compile(
    r"\b(why|how\s+come|reason|explain|did\s*n[o']?t|does\s*n[o']?t|not\s+(?:double|move|follow|rise|reflect)|"
    r"link\w*|relationship|related|correlat\w*|compare|comparison|vs\.?|versus|against|track\w*)\b",
    re.I,
)
_OVERLAY_RE = re.compile(r"\b(overlay|on\s+top|superimpose|add\s+(?:the\s+)?\w+(?:\s+\w+)?\s+(?:to|on)\s+(?:this|the)\s+chart|together|same\s+chart)\b", re.I)


def _last_visual_title(session_state: Any) -> str:
    turns = list(getattr(session_state, "turns", None) or []) if session_state is not None else []
    for t in reversed(turns[-4:]):
        if isinstance(t, dict) and isinstance(t.get("visual"), dict) and t["visual"].get("type") not in (None, "none"):
            return str(t["visual"].get("title") or "")
    return ""


def detect_market_vs_fundamental(query: str, session_state: Any = None) -> Optional[Dict[str, Any]]:
    q = (query or "").strip()
    if not q or not _METRIC_RE.search(q):
        return None
    if re.search(r"\b(dcf|discounted|intrinsic|wacc|what[\s-]+if|run\s+the)\b", q, re.I):
        return None
    stock_on_screen = "NSE:IOC" in _last_visual_title(session_state) or "share price" in _last_visual_title(session_state).lower()
    has_stock = bool(_STOCK_WORD_RE.search(q))
    overlay = bool(_OVERLAY_RE.search(q))
    if not ((has_stock and (_WHY_REL_RE.search(q) or overlay)) or (overlay and stock_on_screen)):
        return None
    ql = q.lower()
    if re.search(r"\b(profit|pat|earnings|net\s+income)\b", ql):
        metric = "pat"
    elif re.search(r"\b(operating\s+cash|ocf)\b", ql):
        metric = "ocf"
    elif re.search(r"\bebitda\b", ql):
        metric = "ebitda"
    else:
        metric = "fcf"
    m = re.search(r"\b(\d{1,2}|five|ten)\s*(?:years?|yrs?)\b", ql)
    years = 5
    if m:
        years = {"five": 5, "ten": 10}.get(m.group(1), None) or int(m.group(1))
    return {"kind": "market_vs_fundamental", "metric": metric, "years": max(3, min(10, years)), "mode": "overlay" if overlay and not _WHY_REL_RE.search(q) else "why"}


_METRIC_META = {
    "fcf": ("free_cash_flow_cr", "Free cash flow (OCF − Capex)"),
    "ocf": ("operating_cash_flow_cr", "Operating cash flow"),
    "pat": ("standalone_pat_cr", "Standalone PAT"),
    "ebitda": ("ebitda_cr", "EBITDA"),
}


def _metric_series(metric: str) -> Dict[str, float]:
    from app.brain.cashflow_trend import _cf_by_fy
    from app.brain.profit_explainer import _pnl_by_fy

    out: Dict[str, float] = {}
    if metric in ("fcf", "ocf"):
        for fy, d in _cf_by_fy().items():
            if "CF.CFO" in d:
                out[fy] = d["CF.CFO"] - (abs(d.get("CAPEX.TOTAL", 0.0)) if metric == "fcf" else 0.0)
    else:
        code = "PL.PAT" if metric == "pat" else "PL.PBIDT"
        for fy, d in _pnl_by_fy().items():
            if code in d:
                out[fy] = d[code]
    return out


def _pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    if len(xs) < 3:
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    return round(num / den, 2) if den else None


def build_market_vs_fundamental_contract(req: Dict[str, Any], persona: str, turn_id: str, language: str, t0: float) -> Dict[str, Any]:
    from app.market.oil_prices import get_oil_prices

    metric = req["metric"]
    key, label = _METRIC_META[metric]
    series = _metric_series(metric)
    ioc = get_oil_prices("iocl")
    px_fy = {p["fy"]: float(p["avg"]) for p in (ioc.get("fy_series") or []) if not p.get("provisional")}
    live_px = float((ioc.get("live") or {}).get("price") or 0) or None
    fys = [fy for fy in sorted(series) if fy in px_fy][-int(req.get("years") or 5):]
    if len(fys) < 3:
        raise RuntimeError("not enough overlapping fiscal years for market vs fundamentals")
    rows = [{"fiscal_year": fy, key: round(series[fy], 2), "ioc_share_price_avg_inr": round(px_fy[fy], 2)} for fy in fys]
    first, last = rows[0], rows[-1]
    m_vals = [r[key] for r in rows]
    p_vals = [r["ioc_share_price_avg_inr"] for r in rows]
    corr = _pearson(m_vals, p_vals)
    neg = [r["fiscal_year"] for r in rows if r[key] < 0]
    avg_metric = sum(m_vals) / len(m_vals)
    px_chg = (p_vals[-1] / p_vals[0] - 1) * 100 if p_vals[0] else 0.0
    mcap_now = (live_px or p_vals[-1]) * SHARES_CR
    mult_last = mcap_now / last[key] if last[key] > 0 else None
    mult_avg = mcap_now / avg_metric if avg_metric > 0 else None
    mult_name = {"fcf": "free cash flow", "ocf": "operating cash flow", "pat": "profit", "ebitda": "EBITDA"}[metric]

    if req.get("mode") == "overlay":
        s1 = (
            f"Here is {label.lower()} by year with IndianOil's average share price from Yahoo Finance on the right axis. "
            f"{label} went from {fmt_inr_cr(first[key])} in {first['fiscal_year']} to {fmt_inr_cr(last[key])} in {last['fiscal_year']}, "
            f"while the average share price moved from ₹{p_vals[0]:.0f} to ₹{p_vals[-1]:.0f}"
            + (f" (correlation {corr:+.2f})." if corr is not None else ".")
        )
        spoken = s1
    else:
        short = label.split(" (")[0]
        if px_chg >= 90:
            # Correct the premise politely when the share price did in fact roughly double
            s1 = (
                f"The share price has in fact roughly doubled too, from a ₹{p_vals[0]:.0f} yearly average in {first['fiscal_year']} to ₹{p_vals[-1]:.0f} in {last['fiscal_year']} ({px_chg:+.0f}%), "
                f"but {short.lower()} grew far faster, from {fmt_inr_cr(first[key])} to {fmt_inr_cr(last[key])}, because {first['fiscal_year']} was an unusually low base "
                "and the market values IOCL on cash flow it can count on through the cycle, not one strong year."
            )
        else:
            s1 = (
                f"{short} went from {fmt_inr_cr(first[key])} in {first['fiscal_year']} to {fmt_inr_cr(last[key])} in {last['fiscal_year']}, "
                f"but the average share price only moved from ₹{p_vals[0]:.0f} to ₹{p_vals[-1]:.0f} ({px_chg:+.0f}%), because the market values IOCL on "
                "cash flow it can count on through the cycle, not one strong year."
            )
        s2 = (
            (f"{short} was negative in {' and '.join(neg)}, " if neg else f"{short} swung sharply from year to year, ")
            + "as refining margins and regulated fuel prices moved, "
            + (f"so at ₹{(live_px or p_vals[-1]):.2f} the market values IOCL at about {mult_last:.1f} times {last['fiscal_year']} {mult_name}"
               + (f" and {mult_avg:.1f} times its {len(rows)}-year average." if mult_avg else ".")
               if mult_last else "so investors discount the latest year.")
        )
        spoken = f"{s1} {s2}"
    display = spoken if len(spoken) <= 590 else spoken[:587].rsplit(" ", 1)[0] + "…"
    title = f"{label} vs IndianOil share price (NSE:IOC yearly average) · {first['fiscal_year']}–{last['fiscal_year']}"
    insights = [
        f"{label}: {fmt_inr_cr(first[key])} ({first['fiscal_year']}) → {fmt_inr_cr(last[key])} ({last['fiscal_year']}); {len(rows)}-year average {fmt_inr_cr(avg_metric)}.",
        f"Share price (yearly average, Yahoo Finance IOC.NS): ₹{p_vals[0]:.2f} → ₹{p_vals[-1]:.2f} ({px_chg:+.1f}%)" + (f"; correlation {corr:+.2f}." if corr is not None else "."),
    ]
    if neg:
        insights.append(f"Negative {mult_name} years: {', '.join(neg)}.")
    if mult_last:
        insights.append(f"Market value ≈ {fmt_inr_cr(mcap_now)} ({SHARES_CR:,.2f} crore shares) = {mult_last:.1f}× {last['fiscal_year']} {mult_name}" + (f", {mult_avg:.1f}× the {len(rows)}-year average." if mult_avg else "."))
    return {
        "contract_version": 3,
        "turn_id": turn_id,
        "language": language,
        "persona": persona,
        "spoken_summary": spoken,
        "display_text": display,
        "visual": {
            "type": "chart",
            "mode": "replace",
            "title": title,
            "subtitle": "Internal: verified Annual Report SSOT (bars) · External: Yahoo Finance IOC.NS yearly average price (line, right axis)",
            "chart": {"kind": "combo", "title": title, "data": rows, "x": "fiscal_year", "y": key, "category": "fiscal_year", "value": key, "unit": "₹ Cr"},
            "table": {"columns": list(rows[0].keys()), "rows": rows, "total_rows": len(rows), "masking": {"level": "none"}},
            "kpis": [
                {"label": f"{label} {last['fiscal_year']}", "value": last[key], "unit": "₹ crore"},
                {"label": "IOC.NS latest close", "value": round(live_px or p_vals[-1], 2), "unit": "₹/share"},
            ] + ([{"label": f"Market value / {mult_name}", "value": round(mult_last, 1), "unit": "×", "delta": f"{last['fiscal_year']}"}] if mult_last else []),
        },
        "insights": insights,
        "insights_v2": [{"kind": k, "text": t} for k, t in zip(["headline", "comparison", "risk", "note"], insights)],
        "context_chips": [
            {"label": persona, "kind": "role"},
            {"label": f"{first['fiscal_year']}–{last['fiscal_year']}", "kind": "period"},
            {"label": "Internal SSOT + Yahoo Finance", "kind": "source"},
        ],
        "sources": [
            {"kind": "data", "object": "fact_snapshot (Standalone SSOT)", "sql": f"{label} by fiscal year"},
            {"kind": "data", "object": "Yahoo Finance API (IOC.NS)", "sql": "Fiscal-year average of daily closes (bonus-adjusted)"},
        ],
        "suggestions": ["Run the DCF valuation model for IOCL", "Show the cash flow trend for the past 10 years", "Why did operating cash flow reduce in FY24-25?"],
        "access": {"status": "allowed"},
        "export_options": ["xlsx", "pdf"],
        "status_events": ["Combined internal SSOT metric with live Yahoo Finance IOC.NS history"],
        "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
    }


# ---------------------------------------------------------------------------------------------- W3: WACC history

_WACC_RE = re.compile(r"\b(wacc|cost\s+of\s+capital|discount\s+rate)\b", re.I)
_WACC_TREND_RE = re.compile(r"\b(past|last|history|historical|trend|over\s+(?:the\s+)?(?:years|time)|each\s+year|by\s+year|\d{1,2}\s*years?|ten\s+years|five\s+years|fy\s?1\d|fy17|decade)\b", re.I)


def detect_wacc_trend(query: str) -> Optional[Dict[str, Any]]:
    q = (query or "").strip()
    if not q or not _WACC_RE.search(q) or not _WACC_TREND_RE.search(q):
        return None
    if re.search(r"\b(instead\s+of|change|set|what[\s-]+if|run|re-?run|re-?evaluat\w*|\d+(?:\.\d+)?\s*%)\b", q, re.I):
        return None
    m = re.search(r"\b(\d{1,2}|five|ten)\s*years?\b", q, re.I)
    years = 10
    if m:
        years = {"five": 5, "ten": 10}.get(m.group(1).lower(), None) or int(m.group(1))
    return {"kind": "wacc_trend", "years": max(2, min(10, years))}


def build_wacc_trend_contract(req: Dict[str, Any], persona: str, turn_id: str, language: str, t0: float) -> Dict[str, Any]:
    from app.finance.dcf.inputs import load_wacc_annual_rows

    def f(v: Any) -> Optional[float]:
        try:
            x = float(v)
            return None if x != x else x
        except (TypeError, ValueError):
            return None

    rows_raw = sorted((r for r in load_wacc_annual_rows() if f(r.get("wacc_pct")) is not None), key=lambda r: str(r.get("fiscal_year")))
    rows_raw = rows_raw[-int(req.get("years") or 10):]
    if len(rows_raw) < 2:
        raise RuntimeError("WACC history unavailable")
    rows: List[Dict[str, Any]] = []
    for r in rows_raw:
        we = f(r.get("weight_equity"))
        rows.append({
            "fiscal_year": str(r.get("fiscal_year")),
            "wacc_pct": round(f(r.get("wacc_pct")) or 0.0, 2),
            "cost_of_equity_pct": round(f(r.get("ke_pct")) or 0.0, 2),
            "pre_tax_cost_of_debt_pct": round(f(r.get("kd_used_pct")) or 0.0, 2),
            "equity_weight_pct": round((we * 100 if we is not None and we <= 1 else (we or 0.0)), 1),
        })
    first, last = rows[0], rows[-1]
    hi = max(rows, key=lambda r: r["wacc_pct"])
    lo = min(rows, key=lambda r: r["wacc_pct"])
    title = f"IOCL WACC by fiscal year · {first['fiscal_year']}–{last['fiscal_year']} (%)"
    spoken = (
        f"IOCL's WACC fell from {first['wacc_pct']:.2f}% in {first['fiscal_year']} to {last['wacc_pct']:.2f}% in {last['fiscal_year']}, "
        f"mainly because the cost of equity came down from {first['cost_of_equity_pct']:.1f}% to {last['cost_of_equity_pct']:.1f}%. "
        f"It was highest in {hi['fiscal_year']} at {hi['wacc_pct']:.2f}% and lowest in {lo['fiscal_year']} at {lo['wacc_pct']:.2f}%."
    )
    chart_rows = [{k: r[k] for k in ("fiscal_year", "wacc_pct", "cost_of_equity_pct", "pre_tax_cost_of_debt_pct")} for r in rows]
    return {
        "contract_version": 3,
        "turn_id": turn_id,
        "language": language,
        "persona": persona,
        "spoken_summary": spoken,
        "display_text": spoken,
        "visual": {
            "type": "chart",
            "mode": "replace",
            "title": title,
            "subtitle": "WACC, cost of equity and pre-tax cost of debt · hrfin_gold.fact_wacc_annual (verified SSOT)",
            "chart": {"kind": "line", "title": title, "data": chart_rows, "x": "fiscal_year", "y": "wacc_pct", "category": "fiscal_year", "value": "wacc_pct", "unit": "%"},
            "table": {"columns": list(rows[0].keys()), "rows": rows, "total_rows": len(rows), "masking": {"level": "none"}},
            "kpis": [
                {"label": f"WACC {last['fiscal_year']}", "value": last["wacc_pct"], "unit": "%"},
                {"label": f"WACC {first['fiscal_year']}", "value": first["wacc_pct"], "unit": "%"},
                {"label": f"Equity weight {last['fiscal_year']}", "value": last["equity_weight_pct"], "unit": "%"},
            ],
        },
        "insights": [
            f"WACC {first['fiscal_year']} {first['wacc_pct']:.2f}% → {last['fiscal_year']} {last['wacc_pct']:.2f}%.",
            f"Cost of equity {first['cost_of_equity_pct']:.2f}% → {last['cost_of_equity_pct']:.2f}%; pre-tax cost of debt {first['pre_tax_cost_of_debt_pct']:.2f}% → {last['pre_tax_cost_of_debt_pct']:.2f}%.",
            f"Equity weight {first['equity_weight_pct']:.1f}% → {last['equity_weight_pct']:.1f}%.",
        ],
        "context_chips": [{"label": persona, "kind": "role"}, {"label": f"{first['fiscal_year']}–{last['fiscal_year']}", "kind": "period"}, {"label": "WACC history", "kind": "subject"}],
        "sources": [{"kind": "data", "object": "hrfin_gold.fact_wacc_annual", "sql": "wacc_pct, ke_pct, kd_used_pct, weight_equity by fiscal_year"}],
        "suggestions": ["Change WACC to 10% and run the DCF again", "What drives the valuation?", "Run the DCF valuation model for IOCL"],
        "access": {"status": "allowed"},
        "export_options": ["xlsx", "pdf"],
        "status_events": [f"Loaded {len(rows)}-year verified WACC history"],
        "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
    }
