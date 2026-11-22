"""Direct crude-oil, FX, GRM, IOC.NS, and retail fuel price questions:
  - Crude / FX / GRM / IOC.NS: daily Yahoo Finance history + live quote (app.market.oil_prices)
  - Retail Fuel RSP (MS Petrol, HSD Diesel, Indane LPG, ATF) across Delhi/Mumbai/Kolkata/Chennai
    & Delhi Tax Build-Up: 10-year monthly series (`FY17–FY27`) from IndianOil / PPAC SSOT history.
Questions that combine oil/fuels with IOCL financial metrics (revenue, PAT, marketing volumes/margins),
what-if scenarios, and screen commands are left alone.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.market.oil_prices import (
    get_daily_history,
    get_delhi_fuel_buildup,
    get_oil_prices,
    get_retail_fuel_prices,
    normalize_benchmark,
)

_OIL = re.compile(
    r"\b(brent|wti|west texas|crude oil price|crude price|oil price|oil prices|crude prices|"
    r"price of (crude|oil)|rupee|usd ?inr|inr|dollar rate|exchange rate|forex|rupee vs (the )?dollar|"
    r"(singapore\s+)?(complex\s+)?grm|crack\s+spread|benchmark\s+refining\s+margin|"
    r"ioc\.?ns|nse:ioc|(iocl|indianoil)\s+(share|stock)(\s+price)?)\b",
    re.I,
)
_ASK = re.compile(r"\b(plot|chart|graph|trend|show|display|history|historical|movement|moved|price|prices|how has|what is|what's|current|today|latest|past|last)\b", re.I)
# leave these to other paths: IOCL metrics (use the overlay), what-if / sensitivity, screen commands
_NOT = re.compile(
    r"\b(revenue|pat|profit|ebitda|income|realisation|realization|margin|cash ?flow|balance sheet|p&l|"
    r"what[- ]if|scenario|sensitivity|impact|if brent|if oil|dcf|valuation|"
    r"overlay|superimpose|on top|remove|hide|export|download)\b",
    re.I,
)
_RETAIL_FUEL = re.compile(
    r"\b(petrol|motor\s+spirit|diesel|high\s+speed\s+diesel|\bhsd\b|\bms\b|"
    r"indane|lpg|cooking\s+gas|cylinder|\batf\b|aviation\s+turbine\s+fuel|jet\s+fuel|"
    r"retail\s+(?:fuel|pump|selling)\s+prices?|pump\s+prices?|fuel\s+prices?)\b",
    re.I,
)
_RETAIL_ASK = re.compile(
    r"\b(plot|chart|graph|trend|show|display|history|historical|movement|moved|price|prices|rate|rates|"
    r"how has|how much|what is|what's|current|today|latest|past|last|compare|comparison|vs|versus|"
    r"across|break\s*down|breakup|build[\s-]?up|split|components?|tax|excise|vat|rsp)\b",
    re.I,
)
_RETAIL_NOT = re.compile(
    r"\b(sales?\s+volume|marketing\s+sales|marketing\s+volume|mmt|market\s+share|throughput|"
    r"excise\s+(?:duty\s+on\s+sale|collection|remitted)|revenue|pat|profit|ebitda|margin)\b",
    re.I,
)
_BUILDUP_RE = re.compile(
    r"\b(build[\s-]?up|break[\s-]?down|breakup|components?|excise|vat|dealer\s+commission|base\s+price|tax\s+share|taxation)\b",
    re.I,
)
_METRO_COMPARE_RE = re.compile(r"\b(metros?|4 cities|four cities|all cities|across cities|city[- ]wise)\b", re.I)
_WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}

# V1 (plan_fix.md v12): IndianOil share-price questions in ANY word order ("stock price of IndianOil",
# "plot the stock market price", "stock mrket price", "IOC.NS") → live Yahoo Finance IOC.NS chart.
_STOCK_RE = re.compile(
    r"\b(?:stock|share|equity)s?\s*(?:market\s*|mrket\s*|mkt\s*)?(?:prices?|movement|chart|trend|performance|quote|value|history)\b"
    r"|\bstock\s*(?:market|mrket)\b"
    r"|\bmarket\s+price\s+of\s+(?:the\s+)?(?:share|stock|iocl|indianoil|indian\s+oil|ioc)\b"
    r"|\bioc\.?ns\b|\bnse\s*:?\s*ioc\b",
    re.I,
)
_STOCK_SHOW_RE = re.compile(r"\b(show|plot|chart|graph|see|display|view|what\s+is|what's|current|today|latest|past|last|history|historical|movement|trend)\b", re.I)
_STOCK_NOT_RE = re.compile(
    r"\b(overlay|superimpose|on\s+top|remove|hide|what[\s-]+if|analysts?|target\s+price|consensus|brokerage|"
    r"instead\s+of|change|set\s+the|use\s+(?:the\s+)?(?:live|current|real[- ]?time))\b",
    re.I,
)
_DCF_WORD_RE = re.compile(r"\b(dcf|discounted\s+cash\s*flow|valuation|intrinsic|undervalued|overvalued)\b", re.I)


def detect_stock_price_plot(query: str) -> Optional[Dict[str, Any]]:
    """IndianOil (NSE:IOC) share price chart request → {'benchmark': 'iocl', 'months': N} or None."""
    q = (query or "").strip()
    if not q or not _STOCK_RE.search(q) or _STOCK_NOT_RE.search(q):
        return None
    if _DCF_WORD_RE.search(q):
        # "Run the DCF on the current share price" is a DCF request; "run a DCF... first, show me the stock price" is a chart
        if not re.search(r"\b(show|plot|chart|see|display)\b[^.?!]{0,40}\b(stock|share)\b", q, re.I):
            return None
    if not _STOCK_SHOW_RE.search(q) and not re.search(r"\bprice\b", q, re.I):
        return None
    return {"benchmark": "iocl", "months": _extract_months(q, default=60)}

_FUEL_DISPLAY: Dict[str, Dict[str, str]] = {
    "MS_PETROL": {"short": "Petrol (MS)", "label": "Motor Spirit (Petrol)", "col": "petrol_rsp_inr_l", "unit": "₹/L"},
    "HSD_DIESEL": {"short": "Diesel (HSD)", "label": "High Speed Diesel (HSD)", "col": "diesel_rsp_inr_l", "unit": "₹/L"},
    "LPG_DOMESTIC": {"short": "Indane LPG (14.2 kg)", "label": "Indane Domestic LPG (14.2 kg)", "col": "lpg_rsp_inr_cyl", "unit": "₹/cylinder"},
    "ATF": {"short": "ATF", "label": "Aviation Turbine Fuel (ATF)", "col": "atf_rsp_inr_kl", "unit": "₹/kL"},
}
_CITY_TITLE = {"DELHI": "Delhi", "MUMBAI": "Mumbai", "KOLKATA": "Kolkata", "CHENNAI": "Chennai"}


def _extract_months(q: str, default: int = 60) -> int:
    months = default
    m = re.search(r"\b(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\s*(years?|yrs?)\b", q, re.I)
    if m:
        n = m.group(1).lower()
        months = 12 * (int(n) if n.isdigit() else _WORDNUM[n])
    else:
        m = re.search(r"\b(\d{1,2})\s*months?\b", q, re.I)
        if m:
            months = int(m.group(1))
        elif re.search(r"\b(a|one|past|last)\s+year\b", q, re.I):
            months = 12
        elif re.search(r"\b(fy17|2016)\b", q, re.I):
            months = 120
    return max(3, min(months, 120))


def _extract_retail_request(q: str) -> Optional[Dict[str, Any]]:
    if not _RETAIL_FUEL.search(q) or not _RETAIL_ASK.search(q) or _NOT.search(q) or _RETAIL_NOT.search(q):
        return None

    fuels: List[str] = []
    if re.search(r"\b(petrol|motor\s+spirit|\bms\b)\b", q, re.I):
        fuels.append("MS_PETROL")
    if re.search(r"\b(diesel|high\s+speed\s+diesel|\bhsd\b)\b", q, re.I):
        fuels.append("HSD_DIESEL")
    if re.search(r"\b(indane|lpg|cooking\s+gas|cylinder)\b", q, re.I):
        fuels.append("LPG_DOMESTIC")
    if re.search(r"\b(\batf\b|aviation\s+turbine\s+fuel|jet\s+fuel)\b", q, re.I):
        fuels.append("ATF")
    if not fuels:
        fuels = ["MS_PETROL", "HSD_DIESEL"]

    cities: List[str] = []
    for c_key in ("DELHI", "MUMBAI", "KOLKATA", "CHENNAI"):
        if re.search(rf"\b{c_key.lower()}\b", q, re.I):
            cities.append(c_key)

    fy_match = re.search(r"\b(FY\d{2})\b", q, re.I)
    fy = fy_match.group(1).upper() if fy_match else None

    if _BUILDUP_RE.search(q) and any(f in ("MS_PETROL", "HSD_DIESEL") for f in fuels):
        bu_fuels = [f for f in fuels if f in ("MS_PETROL", "HSD_DIESEL")]
        return {
            "kind": "fuel_buildup",
            "fuels": bu_fuels,
            "city": "DELHI",
            "fy": fy,
        }

    compare_cities = bool(len(cities) >= 2 or _METRO_COMPARE_RE.search(q))
    if compare_cities:
        if len(cities) < 2:
            cities = ["DELHI", "MUMBAI", "KOLKATA", "CHENNAI"]
        # Multi-city view compares one primary fuel clearly across metros
        fuels = [fuels[0]]
    elif not cities:
        cities = ["DELHI"]

    has_horizon = bool(re.search(r"\b(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\s*(years?|yrs?|months?)\b|\b(history|trend|over time)\b", q, re.I))
    months = _extract_months(q, default=120 if has_horizon else 60)
    point_in_time = bool(compare_cities and not has_horizon and re.search(r"\b(current|today|latest|right now|what is)\b", q, re.I))

    return {
        "kind": "retail_fuel",
        "fuels": fuels,
        "cities": cities,
        "compare_cities": compare_cities,
        "point_in_time": point_in_time,
        "months": months,
    }


def detect_oil_plot(query: str) -> Optional[Dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return None
    retail = _extract_retail_request(q)
    if retail is not None:
        return retail
    stock = detect_stock_price_plot(q)
    if stock is not None:
        return stock
    if not _OIL.search(q) or not _ASK.search(q) or _NOT.search(q):
        return None
    months = _extract_months(q, default=60)
    if re.search(r"\b(ioc\.?ns|nse:ioc|(iocl|indianoil)\s+(share|stock))\b", q, re.I):
        bench = "iocl"
    elif re.search(r"\b((singapore\s+)?(complex\s+)?grm|crack\s+spread|benchmark\s+refining\s+margin)\b", q, re.I):
        bench = "grm"
    elif re.search(r"\b(rupee|usd ?inr|inr|dollar rate|exchange rate|forex)\b", q, re.I) and not re.search(r"\b(brent|wti|crude|oil)\b", q, re.I):
        bench = "inr"
    else:
        bench = "wti" if re.search(r"\b(wti|west texas)\b", q, re.I) else "brent"
    return {"benchmark": normalize_benchmark(bench), "months": months}


def _day_label(d: str) -> str:
    return datetime.strptime(d, "%Y-%m-%d").strftime("%d %b %Y")


def _ym_label(ym: str) -> str:
    return datetime.strptime(ym + "-01", "%Y-%m-%d").strftime("%b %Y")


def _build_retail_fuel_contract(req: Dict[str, Any], persona: str, turn_id: str, language: str, t0: float) -> Dict[str, Any]:
    data = get_retail_fuel_prices()
    all_months: List[str] = data["months"]
    months_n = min(len(all_months), int(req.get("months") or 120))
    sel_months = all_months[-months_n:]
    monthly = data["monthly"]
    fuels: List[str] = req["fuels"]
    cities: List[str] = req["cities"]
    compare_cities = bool(req.get("compare_cities"))
    point_in_time = bool(req.get("point_in_time"))

    yrs = months_n // 12
    period_str = f"last {yrs} years" if months_n % 12 == 0 and yrs > 1 else ("last 12 months" if months_n == 12 else f"last {months_n} months")
    as_of_lbl = _ym_label(sel_months[-1])
    start_lbl = _ym_label(sel_months[0])

    if compare_cities and point_in_time:
        fuel = fuels[0]
        fmeta = _FUEL_DISPLAY[fuel]
        unit = fmeta["unit"]
        rows = [
            {"city": _CITY_TITLE[c], "price": float(monthly[fuel][c][sel_months[-1]])}
            for c in cities
        ]
        hi = max(rows, key=lambda r: r["price"])
        lo = min(rows, key=lambda r: r["price"])
        title = f"IOCL {fmeta['label']} across Indian metros ({unit}) · {as_of_lbl}"
        other_parts = ", ".join(f"{r['city']} ₹{r['price']:,.2f}" for r in rows[1:])
        spoken = (
            f"As of {as_of_lbl}, IndianOil {fmeta['short']} is ₹{rows[0]['price']:,.2f} {unit} in {rows[0]['city']}, "
            f"while {other_parts}. "
            f"{hi['city']} has the highest pump price (₹{hi['price']:,.2f}) and {lo['city']} the lowest (₹{lo['price']:,.2f})."
        )
        insights = [
            f"Spread between highest ({hi['city']} ₹{hi['price']:,.2f}) and lowest ({lo['city']} ₹{lo['price']:,.2f}) is ₹{hi['price'] - lo['price']:,.2f}.",
            f"Inter-city dispersion reflects state-level VAT rates on top of uniform refinery gate + central excise.",
        ]
        kpis = [
            {"label": f"Delhi {fmeta['short']} · {as_of_lbl}", "value": monthly[fuel]["DELHI"][sel_months[-1]], "unit": unit},
            {"label": f"Highest · {hi['city']}", "value": hi["price"], "unit": unit},
            {"label": f"Lowest · {lo['city']}", "value": lo["price"], "unit": unit},
        ]
        chart = {"kind": "bar", "data": rows, "x": "city", "y": "price", "category": "city", "value": "price", "title": title, "unit": unit}
    elif compare_cities:
        fuel = fuels[0]
        fmeta = _FUEL_DISPLAY[fuel]
        unit = fmeta["unit"]
        rows = []
        for ym in sel_months:
            row: Dict[str, Any] = {"date": _ym_label(ym)}
            for c in cities:
                row[c.lower()] = float(monthly[fuel][c][ym])
            rows.append(row)
        y0 = cities[0].lower()
        title = f"IOCL {fmeta['label']} across metros ({unit}) · {start_lbl} – {as_of_lbl}"
        latest_parts = ", ".join(f"{_CITY_TITLE[c]} ₹{monthly[fuel][c][sel_months[-1]]:,.2f}" for c in cities)
        spoken = (
            f"Over the {period_str} ({start_lbl} to {as_of_lbl}), metro {fmeta['short']} prices reached {latest_parts} ({unit})."
        )
        peak_val = max(float(monthly[fuel][cities[0]][ym]) for ym in sel_months)
        low_val = min(float(monthly[fuel][cities[0]][ym]) for ym in sel_months)
        insights = [
            f"{_CITY_TITLE[cities[0]]} {fmeta['short']} ranged from ₹{low_val:,.2f} to ₹{peak_val:,.2f} over {start_lbl}–{as_of_lbl}.",
            f"Current {as_of_lbl} metro prices: {latest_parts}.",
        ]
        kpis = [
            {"label": f"{_CITY_TITLE[c]} {fmeta['short']} · {as_of_lbl}", "value": monthly[fuel][c][sel_months[-1]], "unit": unit}
            for c in cities[:3]
        ]
        chart = {"kind": "line", "data": rows, "x": "date", "y": y0, "category": "date", "value": y0, "title": title, "unit": unit}
    elif len(fuels) >= 2:
        city = cities[0]
        city_lbl = _CITY_TITLE[city]
        unit = _FUEL_DISPLAY[fuels[0]]["unit"]
        same_unit = len({_FUEL_DISPLAY[f]["unit"] for f in fuels}) == 1
        unit_str = unit if same_unit else "₹"
        rows = []
        for ym in sel_months:
            row = {"date": _ym_label(ym)}
            for f in fuels:
                row[_FUEL_DISPLAY[f]["col"]] = float(monthly[f][city][ym])
            rows.append(row)
        primary_col = _FUEL_DISPLAY[fuels[0]]["col"]
        names_joined = " vs ".join(_FUEL_DISPLAY[f]["short"] for f in fuels)
        title = f"{city_lbl} {names_joined} retail prices ({unit_str}) · {start_lbl} – {as_of_lbl}"
        summary_bits = []
        for f in fuels:
            c = _FUEL_DISPLAY[f]["col"]
            vs = [r[c] for r in rows]
            hi_r = rows[max(range(len(vs)), key=lambda i: vs[i])]
            lo_r = rows[min(range(len(vs)), key=lambda i: vs[i])]
            summary_bits.append(
                f"{_FUEL_DISPLAY[f]['short']} moved from ₹{vs[0]:,.2f} ({rows[0]['date']}) to ₹{vs[-1]:,.2f} ({as_of_lbl}), "
                f"peaking at ₹{hi_r[c]:,.2f} ({hi_r['date']}) and bottoming at ₹{lo_r[c]:,.2f} ({lo_r['date']})"
            )
        spread = round(rows[-1][_FUEL_DISPLAY[fuels[0]]["col"]] - rows[-1][_FUEL_DISPLAY[fuels[1]]["col"]], 2) if same_unit else None
        spoken = f"In {city_lbl} over the {period_str}, " + "; ".join(summary_bits) + (
            f". The current {_FUEL_DISPLAY[fuels[0]]['short']}–{_FUEL_DISPLAY[fuels[1]]['short']} spread is ₹{spread:,.2f}."
            if spread is not None else "."
        )
        insights = [
            f"{city_lbl} {_FUEL_DISPLAY[f]['short']}: ₹{rows[0][_FUEL_DISPLAY[f]['col']]:,.2f} ({start_lbl}) → ₹{rows[-1][_FUEL_DISPLAY[f]['col']]:,.2f} ({as_of_lbl})."
            for f in fuels
        ]
        if spread is not None:
            insights.append(f"Current {as_of_lbl} spread between {_FUEL_DISPLAY[fuels[0]]['short']} and {_FUEL_DISPLAY[fuels[1]]['short']} is ₹{spread:,.2f}/L in {city_lbl}.")
        kpis = [
            {"label": f"{city_lbl} {_FUEL_DISPLAY[f]['short']} · {as_of_lbl}", "value": rows[-1][_FUEL_DISPLAY[f]["col"]], "unit": _FUEL_DISPLAY[f]["unit"]}
            for f in fuels[:2]
        ]
        if spread is not None:
            kpis.append({"label": f"{_FUEL_DISPLAY[fuels[0]]['short']} – {_FUEL_DISPLAY[fuels[1]]['short']} spread", "value": spread, "unit": unit_str})
        chart = {"kind": "line", "data": rows, "x": "date", "y": primary_col, "category": "date", "value": primary_col, "title": title, "unit": unit_str}
    else:
        fuel = fuels[0]
        city = cities[0]
        city_lbl = _CITY_TITLE[city]
        fmeta = _FUEL_DISPLAY[fuel]
        unit = fmeta["unit"]
        col = fmeta["col"]
        rows = [{"date": _ym_label(ym), col: float(monthly[fuel][city][ym])} for ym in sel_months]
        vals = [r[col] for r in rows]
        hi_i = max(range(len(vals)), key=lambda i: vals[i])
        lo_i = min(range(len(vals)), key=lambda i: vals[i])
        chg = (vals[-1] - vals[0]) / vals[0] * 100 if vals[0] else 0.0
        title = f"{city_lbl} {fmeta['label']} retail price ({unit}) · {start_lbl} – {as_of_lbl}"
        spoken = (
            f"In {city_lbl}, {fmeta['short']} stood at ₹{vals[-1]:,.2f} {unit} as of {as_of_lbl}. "
            f"Over the {period_str} it moved from ₹{vals[0]:,.2f} ({rows[0]['date']}), peaking at ₹{vals[hi_i]:,.2f} ({rows[hi_i]['date']}) "
            f"and bottoming at ₹{vals[lo_i]:,.2f} ({rows[lo_i]['date']})."
        )
        insights = [
            f"Change over {period_str}: {'+' if chg >= 0 else ''}{chg:.1f}% (₹{vals[0]:,.2f} → ₹{vals[-1]:,.2f}).",
            f"Range: ₹{vals[lo_i]:,.2f} ({rows[lo_i]['date']}) to ₹{vals[hi_i]:,.2f} ({rows[hi_i]['date']}).",
            f"Includes Mar-2024 ₹2/L retail reduction (post-May 2022 central excise cut regime).",
        ]
        kpis = [
            {"label": f"{city_lbl} {fmeta['short']} · {as_of_lbl}", "value": vals[-1], "unit": unit},
            {"label": f"Peak · {rows[hi_i]['date']}", "value": vals[hi_i], "unit": unit},
            {"label": f"Low · {rows[lo_i]['date']}", "value": vals[lo_i], "unit": unit},
        ]
        chart = {"kind": "line", "data": rows, "x": "date", "y": col, "category": "date", "value": col, "title": title, "unit": unit}

    return {
        "turn_id": turn_id,
        "language": language,
        "persona": persona,
        "spoken_summary": spoken,
        "display_text": spoken,
        "visual": {
            "type": "chart",
            "mode": "replace",
            "title": title,
            "subtitle": f"IndianOil (IOCL) / PPAC monthly retail selling price · {period_str.capitalize()}",
            "table": {"columns": list(rows[0].keys()), "rows": rows, "total_rows": len(rows), "masking": {"level": "none"}},
            "chart": chart,
            "kpis": kpis,
        },
        "insights": insights,
        "insights_v2": [{"kind": "trend", "text": s} for s in insights],
        "context_chips": [
            {"label": persona, "kind": "role"},
            {"label": period_str.capitalize(), "kind": "period"},
            {"label": "IOCL / PPAC Metro RSP", "kind": "source"},
        ],
        "sources": [{"kind": "data", "object": "hrfin_gold.fact_retail_fuel_prices", "sql": "IOCL / PPAC Metro Retail Selling Prices (FY17–FY27)"}],
        "suggestions": [
            "Break down the petrol price in Delhi — base price vs central excise vs VAT",
            "Compare petrol prices across Delhi, Mumbai, Kolkata, and Chennai",
            "Show IOCL's P&L statement for FY26",
        ],
        "access": {"status": "allowed"},
        "export_options": ["xlsx", "pdf", "sheets"],
        "status_events": [f"Loaded {len(rows)} retail fuel price points from IOCL / PPAC SSOT history"],
        "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
    }


def _build_fuel_buildup_contract(req: Dict[str, Any], persona: str, turn_id: str, language: str, t0: float) -> Dict[str, Any]:
    records = get_delhi_fuel_buildup()
    fuel = req["fuels"][0]
    fmeta = _FUEL_DISPLAY[fuel]
    fy = req.get("fy")
    fuel_recs = [r for r in records if r["fuel_code"] == fuel]
    target = next((r for r in reversed(fuel_recs) if fy and r["fiscal_year"] == fy), None) or fuel_recs[-1]
    comp_rows = [
        {"component": "Base Price + Freight", "amount_inr_l": target["dealer_invoice_price_inr_l"]},
        {"component": "Central Excise Duty", "amount_inr_l": target["excise_duty_inr_l"]},
        {"component": "Dealer Commission", "amount_inr_l": target["dealer_commission_inr_l"]},
        {"component": "State VAT", "amount_inr_l": target["vat_inr_l"]},
    ]
    rsp = target["rsp_inr_l"]
    tax = target["total_tax_inr_l"]
    tax_pct = target["total_tax_pct"]
    dt_s = target["effective_date"]
    title = f"Delhi {fmeta['label']} Retail Price Build-Up (₹/L) · {dt_s}"
    spoken = (
        f"In Delhi as of {dt_s}, {fmeta['short']} retails at ₹{rsp:,.2f}/L. "
        f"Dealer invoice price (base plus freight) is ₹{target['dealer_invoice_price_inr_l']:,.2f}/L, "
        f"Central Excise Duty is ₹{target['excise_duty_inr_l']:,.2f}/L, Dealer Commission is ₹{target['dealer_commission_inr_l']:,.2f}/L, "
        f"and Delhi VAT is ₹{target['vat_inr_l']:,.2f}/L — meaning Central and State taxes together make up ₹{tax:,.2f}/L ({tax_pct:.1f}% of pump price)."
    )
    insights = [
        f"Total tax wedge (Excise + VAT): ₹{tax:,.2f}/L ({tax_pct:.1f}% of Delhi {fmeta['short']} RSP ₹{rsp:,.2f}/L).",
        f"Central Excise Duty stands at ₹{target['excise_duty_inr_l']:,.2f}/L vs ₹{target['vat_inr_l']:,.2f}/L State VAT.",
        f"Dealer invoice price (refinery transfer + ocean/inland freight) accounts for ₹{target['dealer_invoice_price_inr_l']:,.2f}/L ({100 * target['dealer_invoice_price_inr_l'] / rsp:.1f}%).",
    ]
    return {
        "turn_id": turn_id,
        "language": language,
        "persona": persona,
        "spoken_summary": spoken,
        "display_text": spoken,
        "visual": {
            "type": "chart",
            "mode": "replace",
            "title": title,
            "subtitle": f"IOCL Delhi Price Build-Up ({target['fiscal_year']}) · Central Excise vs State VAT",
            "table": {"columns": list(fuel_recs[0].keys()), "rows": fuel_recs, "total_rows": len(fuel_recs), "masking": {"level": "none"}},
            "chart": {
                "kind": "bar",
                "data": comp_rows,
                "x": "component",
                "y": "amount_inr_l",
                "category": "component",
                "value": "amount_inr_l",
                "title": title,
                "unit": "₹/L",
            },
            "kpis": [
                {"label": f"Delhi {fmeta['short']} RSP", "value": rsp, "unit": "₹/L"},
                {"label": "Central Excise Duty", "value": target["excise_duty_inr_l"], "unit": "₹/L"},
                {"label": "Total Tax (Excise + VAT)", "value": tax, "unit": "₹/L", "delta": f"{tax_pct:.1f}% of pump price"},
            ],
        },
        "insights": insights,
        "insights_v2": [{"kind": "comparison", "text": s} for s in insights],
        "context_chips": [
            {"label": persona, "kind": "role"},
            {"label": target["fiscal_year"], "kind": "period"},
            {"label": "Delhi · Tax Build-Up", "kind": "filter"},
        ],
        "sources": [{"kind": "data", "object": "hrfin_gold.fact_fuel_price_buildup", "sql": "IOCL Delhi Price Build-Up (Base, Freight, Excise, Commission, VAT)"}],
        "suggestions": [
            "Can you show me the petrol or the diesel prices for the past 10 years?",
            "Can you show me the diesel price in Delhi for the past 10 years?",
        ],
        "access": {"status": "allowed"},
        "export_options": ["xlsx", "pdf", "sheets"],
        "status_events": [f"Loaded Delhi {fmeta['short']} tax build-up as of {dt_s}"],
        "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
    }


def build_oil_plot_contract(req: Dict[str, Any], persona: str, turn_id: str, language: str, t0: float) -> Dict[str, Any]:
    if req.get("kind") == "retail_fuel":
        return _build_retail_fuel_contract(req, persona, turn_id, language, t0)
    if req.get("kind") == "fuel_buildup":
        return _build_fuel_buildup_contract(req, persona, turn_id, language, t0)
    d = get_oil_prices(req["benchmark"])
    hist = get_daily_history(req["benchmark"])
    months = req["months"]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=round(months * 30.44))).strftime("%Y-%m-%d")
    days = [(k, v) for k, v in sorted(hist.items()) if k >= cutoff]
    if not days:
        raise RuntimeError("No oil price history for that period.")
    short = d["short"]
    cur = "₹" if d["benchmark"] in ("inr", "iocl") else "$"
    per = "per dollar" if d["benchmark"] == "inr" else ("per share" if d["benchmark"] == "iocl" else "a barrel")
    key = (
        "inr_per_usd"
        if d["benchmark"] == "inr"
        else ("iocl_share_inr" if d["benchmark"] == "iocl" else ("singapore_grm_usd_bbl" if d["benchmark"] == "grm" else f"{d['benchmark']}_usd_bbl"))
    )
    live = d["live"]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    as_of_day = str(live.get("as_of") or "")[:10]
    market_closed = bool(as_of_day) and as_of_day < today  # weekend / holiday: last trading close, not "today"
    rows = [{"date": _day_label(k), key: v} for k, v in days]
    # today's live price as the last point (if the market has moved since the last daily close)
    live_point = bool(live.get("price")) and not d.get("stale") and not market_closed
    if live_point:
        if days[-1][0] == today:
            rows[-1] = {"date": "Today (live)", key: live["price"]}
        else:
            rows.append({"date": "Today (live)", key: live["price"]})
    vals = [r[key] for r in rows]
    hi_i = max(range(len(vals)), key=lambda i: vals[i])
    lo_i = min(range(len(vals)), key=lambda i: vals[i])
    yrs = months // 12
    period = f"last {yrs} years" if months % 12 == 0 and yrs > 1 else ("last 12 months" if months == 12 else f"last {months} months")
    title = f"{d['label']}{'' if d['benchmark'] in ('inr', 'iocl') else ' price'}, daily · {rows[0]['date']} – {_day_label(today)}"
    chg = (vals[-1] - vals[0]) / vals[0] * 100 if vals[0] else 0
    stale = " (from saved history; the live feed is unavailable right now)" if d.get("stale") else ""
    hist_info = d.get("history") or {}
    subj = "The rupee" if d["benchmark"] == "inr" else ("IndianOil (NSE:IOC, live via Yahoo Finance API)" if d["benchmark"] == "iocl" else short)
    when = (
        f"closed at {cur}{live['price']:.2f} {per} on {_day_label(as_of_day)} (latest close; the market is shut today){stale}"
        if market_closed and live.get("price")
        else f"is at {cur}{live['price']:.2f} {per} today{stale}"
    )
    spoken = (
        f"{subj} {when}"
        + (f", {'up' if (live.get('change_pct') or 0) >= 0 else 'down'} {abs(live.get('change_pct') or 0):.1f}% on the day" if live.get("change_pct") is not None and not d.get("stale") else "")
        + f". Over the {period} it moved from {cur}{vals[0]:.2f} on {rows[0]['date']}, peaking at {cur}{vals[hi_i]:.2f} on {rows[hi_i]['date']} "
        f"and bottoming at {cur}{vals[lo_i]:.2f} on {rows[lo_i]['date']}."
    )
    insights = [
        f"Change over the period: {'+' if chg >= 0 else ''}{chg:.0f}% ({rows[0]['date']} to today).",
        f"Range: {cur}{vals[lo_i]:.2f} ({rows[lo_i]['date']}) to {cur}{vals[hi_i]:.2f} ({rows[hi_i]['date']}).",
        (
            "Connected live to Yahoo Finance (IOC.NS): ask \"Run the DCF valuation model for IOCL\" to value IndianOil directly against this live market price."
            if d["benchmark"] == "iocl"
            else (
                "Tip: ask about USD/INR sensitivity to see currency impact on IndianOil's crude import bill."
                if d["benchmark"] == "inr"
                else (
                    "Tip: ask to compare IndianOil's realised refinery GRMs vs Singapore Complex GRM."
                    if d["benchmark"] == "grm"
                    else "Tip: ask for IndianOil revenue or PAT by year and say \"overlay Brent\" or \"overlay GRM\" to compare."
                )
            )
        ),
    ]
    status = (
        f"Live {d['label']} prices: {hist_info.get('saved_days', 0):,} days from saved history + "
        f"{hist_info.get('new_days', 0)} new day(s) fetched from Yahoo Finance"
        if not d.get("stale") else f"Yahoo Finance unreachable: served {len(hist):,} days from saved history"
    )
    return {
        "turn_id": turn_id,
        "language": language,
        "persona": persona,
        "spoken_summary": spoken,
        "display_text": spoken,
        "visual": {
            "type": "chart",
            "mode": "replace",
            "title": title,
            "subtitle": f"{period.capitalize()} · daily closes + today's live price · Yahoo Finance ({d['symbol']})",
            "table": {"columns": ["date", key], "rows": rows, "total_rows": len(rows), "masking": {"level": "none"}},
            "chart": {
                "kind": "line",
                "data": rows,
                "x": "date",
                "y": key,
                "category": "date",
                "value": key,
                "title": title,
                "unit": d["unit"],
            },
            "kpis": [
                {"label": (f"{short} close · {_day_label(as_of_day)}" if market_closed else f"{short} today (live)") if not d.get("stale") else f"{short} last close", "value": live["price"] if live.get("price") else vals[-1], "unit": d["unit"],
                 "delta": (f"{'▲' if (live.get('change_pct') or 0) >= 0 else '▼'} {abs(live.get('change_pct') or 0):.1f}% today") if live.get("change_pct") is not None and not d.get("stale") else "saved history"},
                {"label": f"Highest · {rows[hi_i]['date']}", "value": vals[hi_i], "unit": d["unit"]},
                {"label": f"Lowest · {rows[lo_i]['date']}", "value": vals[lo_i], "unit": d["unit"]},
            ],
        },
        "insights": insights,
        # own takeaways (otherwise the generic engine adds "x% of the total"-style lines that make no sense for prices)
        "insights_v2": [
            {"kind": "trend", "text": insights[0]},
            {"kind": "comparison", "text": insights[1]},
            {"kind": "note", "text": insights[2]},
        ],
        "context_chips": [
            {"label": persona, "kind": "role"},
            {"label": period.capitalize(), "kind": "period"},
            {"label": f"Daily · {d['unit']}", "kind": "filter"},
            {"label": f"Yahoo Finance {d['symbol']}", "kind": "source"},
        ],
        "sources": [{"kind": "data", "object": f"Yahoo Finance {d['symbol']} ({d['label']}{', front-month futures' if d['benchmark'] in ('brent', 'wti') else ''})", "sql": d["source"]}],
        "suggestions": (
            ["Run the DCF valuation model for IOCL", "And what are the analysts saying online?", "Show IndianOil Cash Flow statement for the past 5 years"]
            if d["benchmark"] == "iocl"
            else ["Show IndianOil revenue for the last 10 years", ("Plot Brent for the same period" if d["benchmark"] != "brent" else "Plot Singapore GRM for the same period")]
        ),
        "access": {"status": "allowed"},
        "export_options": ["xlsx", "pdf", "sheets"],
        "status_events": [status],
        "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
    }
