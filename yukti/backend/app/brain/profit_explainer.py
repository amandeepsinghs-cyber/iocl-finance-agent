"""Profit Variance Explainer skill (R1, plan_fix.md).

Answers executive "why" questions about IOCL Standalone profit movements, e.g.
  - "Why was the profit exceptionally low in 24? 25?"
  - "Why is it 12,962? What happened?"  (number-matched to FY25 PAT)
  - "Why did profit jump in FY26?"
with:
  1. Correct period resolution (FY / '24-25' / '2024-25' / quoted PAT values / 'previous year').
  2. An OMC-grouped PAT bridge (net revenue, crude & product cost, opex, D&A + finance, other income &
     exceptional, tax) computed deterministically from verified `fact_snapshot.parquet` (standalone).
  3. Operating context (reported GRM, EBITDA margin, throughput, sales volume, Brent) from the verified
     10-year corporate SSOT (`iocl_10yr_corporate_wide.json`).
  4. A renderer-compatible waterfall (typed total / delta rows) so the screen always changes.
No raw line codes, Indian digit grouping, deterministic numbers only.
"""
from __future__ import annotations

import json
import logging
import re
import time
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from app.brain.inr_format import fmt_inr_cr

logger = logging.getLogger("yukti.brain.profit_explainer")

_FYS = [f"FY{y:02d}" for y in range(17, 27)]
LATEST_FY = "FY26"

_PROFIT_RE = re.compile(r"\b(profits?|pat|pbt|net\s+profit|earnings|bottom[\s-]*line|net\s+income)\b", re.I)
_WHY_RE = re.compile(
    r"\b(why|what\s+happened|what\s+caused|what\s+drove|reasons?|explain|how\s+come|justif\w*|what\s+went\s+wrong)\b", re.I
)
_LOW_RE = re.compile(
    r"\b(low|lower|less|lesser|drop\w*|fell|fall\w*|declin\w*|decreas\w*|reduc\w*|down|dip\w*|weak\w*|poor|exceptionally|different|crash\w*|collaps\w*|slump\w*|shrank|shrink\w*|plung\w*)\b",
    re.I,
)
_HIGH_RE = re.compile(r"\b(high|higher|increas\w*|rose|rise|jump\w*|surg\w*|recover\w*|improv\w*|doubl\w*|tripl\w*|grew|growth)\b", re.I)
_EXCLUDE_RE = re.compile(
    r"\b(dcf|valuation|intrinsic|wacc|what[\s-]+if|scenario|forecast|refiner(?:y|ies)|panipat|paradip|koyali|mathura|haldia|"
    r"barauni|digboi|guwahati|bongaigaon|correlat\w*|brent|stock\s+price|share\s+price|board\s+note|draft)\b",
    re.I,
)
_PREV_YEAR_RE = re.compile(r"\b(previous|last|prior|preceding)\s+year\b", re.I)
_CURRENT_RE = re.compile(r"\b(this|current|latest)\s+year\b", re.I)
_AROUND_RE = re.compile(r"\b(around|about|roughly|approx\w*|nearly|close\s+to)\b", re.I)


# ------------------------------------------------------------------------------------------------ data

def _resolve_asset(rel: str):
    from app.finance.dcf.inputs import _resolve_asset as _ra

    return _ra(rel)


@lru_cache(maxsize=1)
def _pnl_by_fy() -> Dict[str, Dict[str, float]]:
    import pandas as pd
    from app.finance.dcf.inputs import SNAPSHOT_PARQUET

    df = pd.read_parquet(SNAPSHOT_PARQUET)
    mask = df["scope"] == "standalone"
    if "is_latest_vintage" in df.columns:
        mask &= df["is_latest_vintage"] == True  # noqa: E712
    codes = (
        "REV.NET_OF_EXCISE", "PL.REV_OPS", "LEVY.TOTAL", "PL.OTHER_INCOME", "PL.COST_MATERIALS", "PL.PURCHASES_TRADED",
        "PL.INVENTORY_CHANGE", "PL.EMP_BENEFIT", "PL.IMPAIRMENT_FIN_ASSETS", "PL.OTHER_EXP", "PL.PBIDT", "PL.DDA",
        "PL.FIN_COST", "PL.EXCEPTIONAL", "PL.PBT", "PL.TAX", "PL.PAT",
    )
    sub = df[mask & df["line_code"].isin(codes)]
    out: Dict[str, Dict[str, float]] = {}
    for _, r in sub.iterrows():
        v = r.get("value_inr_cr")
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if fv != fv:  # NaN
            continue
        out.setdefault(str(r["fiscal_year"]), {}).setdefault(str(r["line_code"]), fv)
    return out


@lru_cache(maxsize=1)
def _ops_by_fy() -> Dict[str, Dict[str, Any]]:
    try:
        path = _resolve_asset("financial_build/data/iocl_10yr_corporate_wide.json")
        rows = json.loads(path.read_text(encoding="utf-8"))
        return {str(r.get("fiscal_year")): r for r in rows if isinstance(r, dict)}
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"corporate SSOT unavailable for profit explainer context: {exc}")
        return {}


def _prev_fy(fy: str) -> str:
    return f"FY{int(fy[2:]) - 1:02d}"


# ------------------------------------------------------------------------------------------------ detection

_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
)}
_TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}
_SCALES = {"hundred": 100, "thousand": 1000, "lakh": 100000, "lakhs": 100000, "lac": 100000}
_NUMWORD_RUN_RE = re.compile(
    r"\b(?:(?:" + "|".join(list(_UNITS) + list(_TENS) + list(_SCALES)) + r")(?:[\s-]+(?:and[\s-]+)?|\b))+",
    re.I,
)


def _words_to_number(run: str) -> Optional[float]:
    """'twelve thousand nine hundred sixty-two' -> 12962 (Gemini Live spells numbers out when it rewrites queries)."""
    total, cur = 0, 0
    seen = False
    for tok in re.split(r"[\s-]+", run.lower()):
        if not tok or tok == "and":
            continue
        if tok in _UNITS:
            cur += _UNITS[tok]
            seen = True
        elif tok in _TENS:
            cur += _TENS[tok]
            seen = True
        elif tok == "hundred":
            cur = max(cur, 1) * 100
        elif tok in _SCALES:
            total += max(cur, 1) * _SCALES[tok]
            cur = 0
        else:
            return None
    return float(total + cur) if seen or total else None


def _numbers(q: str) -> List[float]:
    vals: List[float] = []
    for m in re.finditer(r"(?<![\w.])(\d{1,3}(?:,\d{2,3})+|\d{4,6})(?:\.\d+)?(?![\w])", q):
        try:
            vals.append(float(m.group(1).replace(",", "")))
        except ValueError:
            pass
    for m in _NUMWORD_RUN_RE.finditer(q):
        v = _words_to_number(m.group(0))
        if v is not None and v >= 1000:
            vals.append(v)
    return vals


def _years_in(q: str) -> List[str]:
    found: List[str] = []

    def add(yy: int) -> None:
        fy = f"FY{yy:02d}"
        if fy in _FYS and fy not in found:
            found.append(fy)

    # "FY24-25" / "FY 2024-25" / "FY2024-2025" → FY25 only (the fiscal year ending in the second number)
    q = re.sub(r"\bfy\s*'?(?:20)?(\d{2})\s*[-–/]\s*(?:20)?(\d{2})\b", lambda m: f"FY{m.group(2)}", q, flags=re.I)
    for m in re.finditer(r"\bfy\s*'?(\d{2})\b", q, re.I):
        add(int(m.group(1)))
    for m in re.finditer(r"\b20(\d{2})\s*[-–/]\s*(?:20)?(\d{2})\b", q):
        add(int(m.group(2)))
    for m in re.finditer(r"(?<![\d,.])(\d{2})\s*[-–/?,.]+\s*(\d{2})(?![\d,])", q):
        a, b = int(m.group(1)), int(m.group(2))
        if b == a + 1:
            add(b)
    for m in re.finditer(r"\b(?:in|for|of|year)\s+(?:the\s+year\s+)?(\d{2})\b", q, re.I):
        add(int(m.group(1)))
    return found


def _years_from_pat_numbers(q: str) -> List[str]:
    pnl = _pnl_by_fy()
    around = bool(_AROUND_RE.search(q))
    out: List[str] = []
    for n in _numbers(q):
        if n < 1000:
            continue
        tol = 0.12 if around else 0.015
        best: Optional[Tuple[float, str]] = None
        for fy in _FYS:
            pat = (pnl.get(fy) or {}).get("PL.PAT")
            if not pat:
                continue
            rel = abs(n - pat) / abs(pat)
            if rel <= tol and (best is None or rel < best[0]):
                best = (rel, fy)
        if best and best[1] not in out:
            out.append(best[1])
    return out


def detect_profit_variance(query: str, session_state: Any = None) -> Optional[Dict[str, Any]]:
    q = (query or "").strip()
    if not q or _EXCLUDE_RE.search(q):
        return None
    if re.search(r"\bcash\b", q, re.I) and not _PROFIT_RE.search(q):
        return None  # cash-flow questions belong to the cash-flow explainer
    try:
        pat_years = _years_from_pat_numbers(q)
    except Exception:  # noqa: BLE001
        pat_years = []
    has_profit = bool(_PROFIT_RE.search(q)) or bool(pat_years)
    has_why = bool(_WHY_RE.search(q))
    low, high = bool(_LOW_RE.search(q)), bool(_HIGH_RE.search(q))

    prev_ctx = getattr(session_state, "last_profit_variance", None) if session_state is not None else None
    last_vis = {}
    turns = list(getattr(session_state, "turns", None) or []) if session_state is not None else []
    if turns and isinstance(turns[-1], dict):
        last_vis = turns[-1].get("visual") or {}
    pnl_on_screen = bool(
        isinstance(last_vis, dict)
        and isinstance(last_vis.get("statement"), dict)
        and last_vis["statement"].get("statement") == "pnl"
    )
    follow_up = bool((prev_ctx or pnl_on_screen) and (has_why or re.search(r"\bdifferent\b", q, re.I)) and (_years_in(q) or pat_years))

    if not ((has_profit and (has_why or (low and pat_years) or (high and pat_years))) or follow_up):
        return None
    # "Not showing a statement" guard: "Show me the profit and loss statement" style requests are not why-questions
    if not has_why and not follow_up and not (low or high):
        return None
    # V3: reuse the year from the previous user question when this one names none ("…in 2024-25?" → "why did profit fall?")
    ctx_years: List[str] = []
    if not _years_in(q) and not pat_years and session_state is not None:
        ctx_years = _years_in(str(getattr(session_state, "last_user_query", "") or ""))
    return {"kind": "profit_variance", "years": _years_in(q) or ctx_years, "pat_years": pat_years, "low": low, "high": high,
            "prev_ctx": prev_ctx, "query": q}


def resolve_periods(match: Dict[str, Any]) -> Tuple[str, str]:
    pnl = _pnl_by_fy()
    q = match.get("query") or ""
    years: List[str] = list(match.get("years") or [])
    pat_years: List[str] = list(match.get("pat_years") or [])
    low, high = match.get("low"), match.get("high")
    candidates = [y for y in years + pat_years if y in pnl]
    # If the user names the latest year only as a contrast ("it is 36,802 ... why is it 12,962"), focus on the other year
    if len(candidates) > 1 and LATEST_FY in candidates:
        others = [c for c in candidates if c != LATEST_FY]
        if others:
            candidates = others
    target: Optional[str] = None
    if candidates:
        if low and not high:
            target = min(candidates, key=lambda fy: pnl[fy].get("PL.PAT", 0.0))
        elif high and not low:
            target = max(candidates, key=lambda fy: pnl[fy].get("PL.PAT", 0.0))
        else:
            target = candidates[0]
    elif _PREV_YEAR_RE.search(q):
        target = _prev_fy(LATEST_FY)
    elif match.get("prev_ctx"):
        target = match["prev_ctx"].get("fy_to")
    elif low and not high:
        # most recent year in which PAT fell YoY
        for fy in reversed(_FYS[1:]):
            cur, prv = pnl.get(fy, {}).get("PL.PAT"), pnl.get(_prev_fy(fy), {}).get("PL.PAT")
            if cur is not None and prv is not None and cur < prv:
                target = fy
                break
    if not target or target == _FYS[0]:
        target = LATEST_FY
    return _prev_fy(target), target


# ------------------------------------------------------------------------------------------------ bridge

_BUCKETS = [
    ("net_rev", "Net revenue (ex-excise)"),
    ("cogs", "Crude & product cost"),
    ("emp", "Employee cost"),
    ("opex", "Other opex & impairment"),
    ("dda_fin", "Depreciation & finance cost"),
    ("oi_exc", "Other income & exceptional items"),
    ("tax", "Tax"),
]


def _bucket_values(p: Dict[str, float]) -> Dict[str, float]:
    g = lambda k: float(p.get(k, 0.0) or 0.0)  # noqa: E731
    return {
        "net_rev": g("REV.NET_OF_EXCISE") or (g("PL.REV_OPS") - g("LEVY.TOTAL")),
        "cogs": g("PL.COST_MATERIALS") + g("PL.PURCHASES_TRADED") + g("PL.INVENTORY_CHANGE"),
        "emp": g("PL.EMP_BENEFIT"),
        "opex": g("PL.OTHER_EXP") + g("PL.IMPAIRMENT_FIN_ASSETS"),
        "dda_fin": g("PL.DDA") + g("PL.FIN_COST"),
        "oi_exc": g("PL.OTHER_INCOME") + g("PL.EXCEPTIONAL"),
        "tax": g("PL.TAX"),
    }


def compute_pat_bridge(fy_from: str, fy_to: str) -> Dict[str, Any]:
    pnl = _pnl_by_fy()
    a, b = pnl.get(fy_from) or {}, pnl.get(fy_to) or {}
    if "PL.PAT" not in a or "PL.PAT" not in b:
        raise ValueError(f"PAT not available for {fy_from}/{fy_to}")
    va, vb = _bucket_values(a), _bucket_values(b)
    cost_keys = {"cogs", "emp", "opex", "dda_fin", "tax"}
    impacts: Dict[str, float] = {}
    for k, _ in _BUCKETS:
        d = vb[k] - va[k]
        impacts[k] = -d if k in cost_keys else d
    pat_a, pat_b = a["PL.PAT"], b["PL.PAT"]
    residual = (pat_b - pat_a) - sum(impacts.values())
    return {
        "fy_from": fy_from, "fy_to": fy_to, "pat_from": pat_a, "pat_to": pat_b,
        "pbt_from": a.get("PL.PBT"), "pbt_to": b.get("PL.PBT"),
        "ebitda_from": a.get("PL.PBIDT"), "ebitda_to": b.get("PL.PBIDT"),
        "levels_from": va, "levels_to": vb, "impacts": impacts, "residual": residual,
        "gross_margin_impact": impacts["net_rev"] + impacts["cogs"],
        "exceptional_from": a.get("PL.EXCEPTIONAL", 0.0), "exceptional_to": b.get("PL.EXCEPTIONAL", 0.0),
    }


def _pct(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a in (None, 0) or b is None:
        return None
    return (b - a) / abs(a) * 100.0


def _ops(fy: str) -> Dict[str, Any]:
    return _ops_by_fy().get(fy) or {}


def build_narrative(br: Dict[str, Any]) -> Tuple[str, str, List[str], str]:
    fy_from, fy_to = br["fy_from"], br["fy_to"]
    imp = br["impacts"]
    pat_a, pat_b = br["pat_from"], br["pat_to"]
    chg = _pct(pat_a, pat_b) or 0.0
    fell = pat_b < pat_a
    o_a, o_b = _ops(fy_from), _ops(fy_to)
    grm_a, grm_b = o_a.get("gross_refining_margin_usd_bbl"), o_b.get("gross_refining_margin_usd_bbl")
    em_a = (br["ebitda_from"] / br["levels_from"]["net_rev"] * 100) if br.get("ebitda_from") and br["levels_from"]["net_rev"] else None
    em_b = (br["ebitda_to"] / br["levels_to"]["net_rev"] * 100) if br.get("ebitda_to") and br["levels_to"]["net_rev"] else None
    vol_a, vol_b = o_a.get("marketing_sales_mmt"), o_b.get("marketing_sales_mmt")
    gm = br["gross_margin_impact"]
    rev_d = imp["net_rev"]
    cost_d = -imp["cogs"]  # change in crude & product cost (positive = cost rose)

    margin_driven = abs(gm) >= 0.5 * abs(pat_b - pat_a)
    verb = "fell" if fell else "rose"
    s1 = (
        f"IOCL's standalone profit after tax {verb} from {fmt_inr_cr(pat_a)} in {fy_from} to {fmt_inr_cr(pat_b)} in {fy_to} "
        f"({f'{chg:+.0f}'.replace('-', '−')}%)"
    )
    if margin_driven:
        s1 += ", mainly because refining and marketing margins " + ("collapsed" if fell else "recovered")
        if vol_a and vol_b:
            s1 += f", not because of volumes, which {'rose' if vol_b >= vol_a else 'eased'} to {vol_b:.1f} MMT of sales"
    s1 += "."

    rev_phrase = f"revenue net of excise {'fell' if rev_d < 0 else 'rose'} by {fmt_inr_cr(abs(rev_d))}"
    cost_phrase = f"crude and product costs {'fell' if cost_d < 0 else 'rose'} by {fmt_inr_cr(abs(cost_d))}"
    s2 = f"{rev_phrase.capitalize()} while {cost_phrase}, so the gross margin {'shrank' if gm < 0 else 'widened'} by {fmt_inr_cr(abs(gm))}"
    if grm_a is not None and grm_b is not None:
        s2 += f"; the reported refining margin (GRM) went from ${grm_a:.2f} to ${grm_b:.2f} a barrel"
    if em_a is not None and em_b is not None:
        s2 += f" and EBITDA margin from {em_a:.1f}% to {em_b:.1f}%"
    s2 += "."

    cushions = []
    labels = dict(_BUCKETS)
    for k in ("emp", "opex", "dda_fin", "oi_exc", "tax"):
        v = imp[k]
        if abs(v) <= 500 or v * (pat_b - pat_a) >= 0:
            continue
        if k == "oi_exc":
            exc_a, exc_b = br.get("exceptional_from") or 0.0, br.get("exceptional_to") or 0.0
            if v > 0 and exc_b > 0:
                cushions.append(f"higher other income and a {fmt_inr_cr(exc_b)} exceptional gain ({fmt_inr_cr(v)})")
            elif v < 0 and exc_a > 0 and exc_b <= 0:
                cushions.append(f"the absence of the previous year's {fmt_inr_cr(exc_a)} exceptional gain ({fmt_inr_cr(abs(v))})")
            else:
                cushions.append(f"{'higher' if v > 0 else 'lower'} other income ({fmt_inr_cr(abs(v))})")
        else:
            # cost buckets: positive impact = cost fell
            cushions.append(f"{'lower' if v > 0 else 'higher'} {labels[k].lower()} ({fmt_inr_cr(abs(v))})")
    s3_parts = []
    if cushions:
        s3_parts.append("partly offset by " + ", ".join(cushions[:-1]) + (" and " if len(cushions) > 1 else "") + cushions[-1])
    pnl = _pnl_by_fy()
    if fy_to != LATEST_FY and LATEST_FY in pnl:
        latest_pat = pnl[LATEST_FY].get("PL.PAT")
        grm_l = _ops(LATEST_FY).get("gross_refining_margin_usd_bbl")
        s3_parts.append(
            f"profit has since {'recovered' if latest_pat and latest_pat > pat_b else 'moved'} to {fmt_inr_cr(latest_pat)} in {LATEST_FY}"
            + (f" as GRM rebounded to ${grm_l:.2f}" if grm_l and grm_b is not None and grm_l > grm_b else "")
        )
    s3 = ""
    if s3_parts:
        s3 = "; ".join(s3_parts)
        s3 = s3[0].upper() + s3[1:] + "."

    display = " ".join(x for x in (s1, s2, s3) if x)
    # V5 (plan_fix.md v12): contract display_text maxLength is 600 — never let the screen cut mid-word
    if len(display) > 560 and s3_parts:
        short_s3 = s3_parts[-1] if fy_to != LATEST_FY else ""
        display = " ".join(x for x in (s1, s2, (short_s3[0].upper() + short_s3[1:] + ".") if short_s3 else "") if x)
    if len(display) > 560:
        display = f"{s1} {s2}"
    if len(display) > 590:
        display = display[:587].rsplit(" ", 1)[0] + "…"
    # Voice: keep it to ~2 crisp sentences so Live never cuts off mid-answer
    spoken_s2 = (
        f"The gross margin {'shrank' if gm < 0 else 'widened'} by {fmt_inr_cr(abs(gm))} as "
        + (f"GRM moved from ${grm_a:.2f} to ${grm_b:.2f} a barrel" if grm_a is not None and grm_b is not None else "crude and product costs moved out of line with revenue")
        + (f", and {s3_parts[-1]}" if fy_to != LATEST_FY and s3_parts else "")
        + "."
    )
    spoken = f"{s1} {spoken_s2}"
    # Alternate angle used when the same bridge is asked about again (never repeat verbatim)
    alt_spoken = f"{s2} {s3}".strip()

    insights = [
        f"PAT {fy_from} {fmt_inr_cr(pat_a)} → {fy_to} {fmt_inr_cr(pat_b)} ({chg:+.1f}%).",
        f"Gross margin impact (net revenue {fmt_inr_cr(rev_d, signed=True)} vs crude & product cost change {fmt_inr_cr(cost_d, signed=True)}): {fmt_inr_cr(gm, signed=True)}.",
    ]
    if grm_a is not None and grm_b is not None:
        insights.append(f"Reported GRM ${grm_a:.2f} → ${grm_b:.2f}/bbl" + (f"; EBITDA margin {em_a:.1f}% → {em_b:.1f}%." if em_a and em_b else "."))
    if cushions:
        insights.append("Offsets: " + "; ".join(cushions) + ".")
    return spoken, display, insights, alt_spoken


def build_waterfall(br: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = [{"step": f"{br['fy_from']} PAT", "label": f"{br['fy_from']} PAT", "amount_cr": round(br["pat_from"], 2), "value": round(br["pat_from"], 2), "type": "total"}]
    for k, lbl in _BUCKETS:
        v = round(br["impacts"][k], 2)
        rows.append({"step": lbl, "label": lbl, "amount_cr": v, "value": v, "type": "delta"})
    if abs(br["residual"]) >= 1.0:
        v = round(br["residual"], 2)
        rows.append({"step": "Other / rounding", "label": "Other / rounding", "amount_cr": v, "value": v, "type": "delta"})
    rows.append({"step": f"{br['fy_to']} PAT", "label": f"{br['fy_to']} PAT", "amount_cr": round(br["pat_to"], 2), "value": round(br["pat_to"], 2), "type": "total"})
    return rows


def answer_profit_variance(
    match: Dict[str, Any],
    session_state: Any,
    persona: str,
    turn_id: str,
    language: str,
    t0: float,
    prefix: str = "",
) -> Dict[str, Any]:
    fy_from, fy_to = resolve_periods(match)
    br = compute_pat_bridge(fy_from, fy_to)
    spoken, display, insights, alt_spoken = build_narrative(br)

    # Repeat guard: if the same bridge was just explained, answer from a different angle (never verbatim)
    prev = getattr(session_state, "last_profit_variance", None) if session_state is not None else None
    turns = list(getattr(session_state, "turns", None) or []) if session_state is not None else []
    last_spoken = (turns[-1].get("spoken_summary") or "").strip() if turns and isinstance(turns[-1], dict) else ""
    if (prev and prev.get("fy_from") == fy_from and prev.get("fy_to") == fy_to) or last_spoken.endswith(spoken.strip()):
        spoken = f"On screen is the {fy_from} to {fy_to} profit bridge. {alt_spoken}"
    if prefix:
        spoken = f"{prefix} {spoken}"
        if len(prefix) + 1 + len(display) <= 595:
            display = f"{prefix} {display}"

    o_a, o_b = _ops(fy_from), _ops(fy_to)
    title = f"Why {fy_to} profit {'fell' if br['pat_to'] < br['pat_from'] else 'rose'}: PAT bridge {fy_from} → {fy_to} (₹ crore)"
    rows = build_waterfall(br)
    kpis = [
        {"label": f"PAT {fy_from}", "value": round(br["pat_from"], 2), "unit": "₹ crore"},
        {"label": f"PAT {fy_to}", "value": round(br["pat_to"], 2), "unit": "₹ crore", "delta": f"{(_pct(br['pat_from'], br['pat_to']) or 0):+.1f}% YoY"},
    ]
    if o_a.get("gross_refining_margin_usd_bbl") is not None and o_b.get("gross_refining_margin_usd_bbl") is not None:
        kpis.append({
            "label": f"Reported GRM {fy_to}", "value": o_b["gross_refining_margin_usd_bbl"], "unit": "$/bbl",
            "delta": f"from ${o_a['gross_refining_margin_usd_bbl']:.2f} in {fy_from}",
        })
    table_rows = [{"driver": r["step"], "impact_on_pat_cr": r["amount_cr"], "type": r["type"]} for r in rows]

    if session_state is not None:
        try:
            session_state.last_profit_variance = {"fy_from": fy_from, "fy_to": fy_to, "query": match.get("query")}
        except Exception:  # noqa: BLE001
            pass

    src_doc = o_b.get("source_doc") or "IOCL_AR_FY2025-26.pdf"
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
            "subtitle": "Standalone · verified Schedule III SSOT · positive bars add to profit, negative bars reduce it",
            "chart": {
                "kind": "waterfall", "title": title, "x": "step", "y": "amount_cr", "category": "step", "value": "amount_cr",
                "unit": "₹ Cr", "sort": "none", "bridge_version": "v3", "period": f"{fy_from}→{fy_to}", "data": rows,
            },
            "table": {"columns": ["driver", "impact_on_pat_cr", "type"], "rows": table_rows, "total_rows": len(table_rows), "masking": {"level": "none"}},
            "kpis": kpis,
        },
        "insights": insights,
        "insights_v2": [{"kind": k, "text": t} for k, t in zip(["headline", "comparison", "trend", "note"], insights)],
        "context_chips": [
            {"label": persona, "kind": "role"},
            {"label": f"{fy_from} → {fy_to}", "kind": "period"},
            {"label": "PAT variance bridge", "kind": "subject"},
        ],
        "sources": [
            {"kind": "data", "object": "fact_snapshot (Standalone Schedule III)", "sql": f"PAT bridge {fy_from}→{fy_to}", "title": f"{src_doc} p.{o_b.get('pl_page', '')}".strip()},
            {"kind": "data", "object": "iocl_10yr_corporate_wide (GRM, volumes)", "title": "IOCL 10-year corporate SSOT"},
        ],
        "suggestions": [
            f"Show the {fy_to} P&L as a waterfall",
            "Compare GRM across IOCL refineries for " + fy_to,
            "Show the cash flow trend for the past 10 years",
        ],
        "access": {"status": "allowed"},
        "export_options": ["xlsx", "sheets", "pdf"],
        "status_events": [f"Computed verified PAT bridge {fy_from}→{fy_to} with GRM & margin context"],
        "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
    }
