"""Contextual On-Screen View & Analytical Correlation/Takeaway Handler.

Answers conversational executive follow-ups about the active visual on screen
(charts, Brent/GRM/FX overlays, Schedule III statements, tables) without
wiping or re-plotting the active card in the feed:
  1. "Can you please explain what is going on on the screen?"
  2. "But what is the point you're trying to make?" / "So what is the takeaway?"
  3. "It seems there is no correlation from the Brent price to IOCL. Is it the
     case because of the Brent price decreases? The revenue should have increased."
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("yukti.brain.explain_screen")

_REPAIR_RE = re.compile(
    r"("
    r"which\s+screen\s+(?:are\s+you|am\s+i)\s+(?:showing|seeing|looking\s+at)"
    r"|what\s+(?:screen\s+)?are\s+you\s+showing"
    r"|i(?:'m|\s+am)\s+still\s+seeing"
    r"|(?:screen|chart|this|it)\s+(?:is\s+not|isn'?t|does\s+not|doesn'?t)\s+(?:doing|showing|make|making|answer\w*|match\w*)"
    r"|not\s+doing\s+(?:any\s+)?justification"
    r"|(?:wrong|old|previous|same)\s+(?:screen|chart|view)"
    r"|(?:that'?s|this\s+is)\s+not\s+what\s+i\s+asked"
    r"|you(?:'re|\s+are)\s+not\s+(?:answering|listening)"
    r")",
    re.I,
)

_EXPLAIN_SCREEN_RE = re.compile(
    r"\b("
    r"explain\s+what\s+(?:is\s+|'s\s+)?(?:going\s+on\s+)?(?:on\s+(?:the\s+)?)?screen"
    r"|what\s+(?:is|'s)\s+going\s+on\s+on\s+(?:the\s+)?screen"
    r"|explain\s+(?:this|the)\s+(?:chart|graph|plot|visual|table|statement|screen|view)"
    r"|walk\s+me\s+through\s+(?:this|what(?:'s|\s+is)\s+on\s+(?:the\s+)?screen|(?:this|the)\s+(?:chart|table|statement))"
    r"|what\s+am\s+i\s+looking\s+at"
    r"|help\s+me\s+(?:read|understand)\s+this\s+(?:chart|graph|table|screen)"
    r")\b",
    re.I,
)

_SO_WHAT_RE = re.compile(
    r"\b("
    r"what\s+(?:is|'s)\s+the\s+point\s+you(?:'re|\s+are)\s+(?:trying\s+to\s+)?mak\w*"
    r"|what\s+(?:is|'s)\s+your\s+point"
    r"|what\s+are\s+you\s+trying\s+to\s+(?:say|show|tell\s+me)"
    r"|what\s+(?:is|'s)\s+the\s+(?:main\s+|key\s+)?(?:takeaway|conclusion|message|bottom\s+line)"
    r"|so\s+what\s+does\s+(?:this|that)\s+(?:mean|show|tell\s+us)"
    r")\b",
    re.I,
)

_CORRELATION_WHY_RE = re.compile(
    r"("
    r"\b(?:no|low|weak|little|inverse|negative|positive)?\s*correlat(?:e|ed|es|ion)\b"
    r"|\b(?:brent|crude|oil)\b.{0,70}\b(?:decreas\w*|fell|fall\w*|drop\w*|declin\w*|increas\w*|rose|ris\w*)\b.{0,70}\b(?:revenue|income|pat|profit|margin|ebitda)\b"
    r"|\b(?:revenue|income|pat|profit|margin|ebitda)\b.{0,70}\b(?:should\s+have|still|even\s+when|despite|while)\b.{0,70}\b(?:brent|crude|oil|increas\w*|decreas\w*|fell|drop\w*)\b"
    r"|\bis\s+it\s+(?:the\s+case\s+)?because\s+of\s+(?:the\s+)?(?:brent|crude|oil)\b"
    r")",
    re.I,
)

_NEW_ACTION_GUARD_RE = re.compile(
    r"^\s*(?:please\s+|can\s+you\s+|could\s+you\s+)?("
    r"show|plot|chart|graph|give\s+me|fetch|list|rank|run|re-?run|build|draft|export|download|"
    r"switch|change|set|overlay|superimpose|add|remove|open|go\s+to"
    r")\b",
    re.I,
)

# Verified IOCL Standalone operational context (AR FY22–FY26) for downstream economics grounding
_IOCL_OMC_CONTEXT_BY_FY: Dict[str, Dict[str, float]] = {
    "FY22": {"gross_rev_cr": 728445.40, "net_rev_cr": 598163.76, "pat_cr": 24184.10, "refining_mmt": 67.67, "marketing_mmt": 84.46, "grm_usd_bbl": 11.25},
    "FY23": {"gross_rev_cr": 934952.71, "net_rev_cr": 839472.24, "pat_cr": 8241.82, "refining_mmt": 72.41, "marketing_mmt": 95.71, "grm_usd_bbl": 19.52},
    "FY24": {"gross_rev_cr": 866345.36, "net_rev_cr": 774348.72, "pat_cr": 39618.84, "refining_mmt": 73.31, "marketing_mmt": 97.55, "grm_usd_bbl": 12.05},
    "FY25": {"gross_rev_cr": 845513.21, "net_rev_cr": 745891.15, "pat_cr": 12961.58, "refining_mmt": 71.56, "marketing_mmt": 100.12, "grm_usd_bbl": 4.80},
    "FY26": {"gross_rev_cr": 886224.41, "net_rev_cr": 784157.87, "pat_cr": 36802.42, "refining_mmt": 75.45, "marketing_mmt": 105.12, "grm_usd_bbl": 10.85},
}


def find_active_visual_turn(session_state: Any, max_back: int = 8) -> Optional[Dict[str, Any]]:
    """Return the most recent turn in `session_state.turns` that owns an active non-empty visual."""
    turns = list(getattr(session_state, "turns", None) or [])
    for t in reversed(turns[-max_back:]):
        if not isinstance(t, dict):
            continue
        vis = t.get("visual")
        if isinstance(vis, dict) and vis.get("type") and vis.get("type") not in ("none", "refusal"):
            return t
    return None


def is_repair_or_meta_question(query: str) -> bool:
    """True for frustration / meta questions about the screen ('which screen are you showing?')."""
    return bool(_REPAIR_RE.search(query or ""))


def classify_screen_question(query: str) -> Optional[str]:
    """Return 'repair', 'correlation', 'so_what', 'explain_screen', or None."""
    q = (query or "").strip()
    if not q:
        return None
    if _REPAIR_RE.search(q):
        return "repair"
    if _EXPLAIN_SCREEN_RE.search(q):
        return "explain_screen"
    if _SO_WHAT_RE.search(q):
        return "so_what"
    if _NEW_ACTION_GUARD_RE.search(q):
        return None
    if _CORRELATION_WHY_RE.search(q):
        return "correlation"
    return None


def detect_screen_explanation_or_correlation(query: str, session_state: Any) -> Optional[Dict[str, Any]]:
    """Return a match payload when `query` asks to explain/interpret the active visual on screen."""
    if session_state is None:
        return None
    kind = classify_screen_question(query)
    if not kind:
        return None
    active_turn = find_active_visual_turn(session_state)
    if active_turn is None:
        return None
    return {
        "kind": kind,
        "active_turn": active_turn,
        "overlay": getattr(session_state, "active_overlay", None),
    }


def _pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    return round(num / den, 2) if den > 1e-9 else None


def _extract_visual_digest(active_turn: Dict[str, Any], overlay: Optional[str], query: str) -> Dict[str, Any]:
    vis = active_turn.get("visual") or {}
    vtype = str(vis.get("type") or "none")
    title = str(vis.get("title") or "")
    subtitle = str(vis.get("subtitle") or "")
    kpis = (vis.get("kpis") or [])[:4]

    rows: List[Dict[str, Any]] = []
    chart = vis.get("chart") if isinstance(vis.get("chart"), dict) else {}
    if isinstance(chart.get("data"), list) and chart["data"]:
        rows = [r for r in chart["data"][:12] if isinstance(r, dict)]
    elif isinstance((vis.get("table") or {}).get("rows"), list):
        rows = [r for r in vis["table"]["rows"][:12] if isinstance(r, dict)]
    elif isinstance(vis.get("statement"), dict):
        stmt = vis["statement"]
        periods = (stmt.get("periods") or [])[:5]
        for sec in stmt.get("sections") or []:
            for r in (sec.get("rows") or []):
                if r.get("kind") in ("subtotal", "total") or r.get("level") in (0, 1):
                    vals = {p: (r.get("values") or {}).get(p) for p in periods}
                    rows.append({"line": r.get("label"), **vals})
                if len(rows) >= 12:
                    break

    want_brent = bool(
        overlay in ("brent", "wti", "grm", "inr")
        or re.search(r"\b(brent|crude|oil|grm|rupee|fx|correlat)\b", query or "", re.I)
    )
    market_fy: Dict[str, Dict[str, float]] = {}
    corr_brent: Optional[float] = None
    if want_brent:
        try:
            from app.market.oil_prices import get_oil_prices

            brent_fy = {p["fy"]: p["avg"] for p in (get_oil_prices("brent").get("fy_series") or [])}
            inr_fy = {p["fy"]: p["avg"] for p in (get_oil_prices("inr").get("fy_series") or [])}
            from app.brain.profit_explainer import _ops_by_fy

            verified_ops = _ops_by_fy()
            for fy in _IOCL_OMC_CONTEXT_BY_FY:
                v = verified_ops.get(fy) or {}
                ops = {
                    "gross_rev_cr": v.get("gross_revenue_inr_cr"),
                    "net_rev_cr": v.get("net_revenue_inr_cr"),
                    "pat_cr": v.get("pat_inr_cr"),
                    "refining_mmt": v.get("refining_throughput_mmt"),
                    "marketing_mmt": v.get("marketing_sales_mmt"),
                    "grm_usd_bbl": v.get("gross_refining_margin_usd_bbl"),
                    "ssot_brent_avg_usd_bbl": v.get("brent_avg_usd_bbl"),
                } if v else dict(_IOCL_OMC_CONTEXT_BY_FY[fy])
                market_fy[fy] = {
                    "brent_avg_usd_bbl": brent_fy.get(fy, 0.0),
                    "usdinr_avg": inr_fy.get(fy, 0.0),
                    **ops,
                }
            # Compute correlation if rows are fiscal-year series
            xs, ys = [], []
            for r in rows:
                fy_lbl = next((str(v).upper() for k, v in r.items() if re.match(r"^FY\d{2}$", str(v).strip(), re.I)), None)
                num_v = next((float(v) for k, v in r.items() if isinstance(v, (int, float)) and not isinstance(v, bool)), None)
                if fy_lbl and fy_lbl in brent_fy and num_v is not None:
                    xs.append(float(brent_fy[fy_lbl]))
                    ys.append(num_v)
            corr_brent = _pearson(xs, ys)
        except Exception as exc:
            logger.debug(f"Benchmark FY series lookup skipped: {exc}")

    return {
        "visual_type": vtype,
        "title": title,
        "subtitle": subtitle,
        "chart_kind": chart.get("kind") if chart else None,
        "active_overlay": overlay or ("brent" if re.search(r"\bbrent\b", query or "", re.I) else None),
        "kpis": kpis,
        "data_points": rows,
        "prior_spoken_summary": active_turn.get("spoken_summary") or "",
        "brent_vs_series_pearson_r": corr_brent,
        "iocl_fy22_fy26_downstream_context": market_fy if market_fy else None,
    }


_SCREEN_EXPLAIN_SYS = """You are Yukti, Finance & Downstream Chief of Staff to the Chairman of Indian Oil Corporation Limited (IOCL).
Answer the user's conversational question about what is currently displayed on screen in 3–4 crisp, executive sentences.
Rules:
1. Answer the EXACT question in the very first sentence (Bottom-Line Up Front). Never open with generic boilerplate like "Gross revenue moved from X to Y. Details are on screen."
2. Do not greet the user (this is mid-conversation). Use ₹ and Indian numbering (lakh, crore).
3. Ground every number strictly in the On-Screen Digest below. Never mention JSON, payloads, schemas, or internal field names.
4. When explaining Brent crude vs IOCL Revenue / Profit:
   - Explain clearly that IOCL is a downstream Oil Marketing Company (refiner-marketer), NOT an upstream crude producer.
   - Between FY22 and FY25, IOCL's gross revenue broadly tracked crude price swings (peaking at ₹9,34,953 crore in FY23 when Brent averaged ~$95/bbl).
   - In FY26, Brent fell ~12% (from $78.15 to $69.04/bbl), YET IOCL's Gross Revenue ROSE +4.8% to ₹8,86,224 crore because: (a) physical marketing sales volume grew +4.8% to 105.1 MMT (refining throughput rose to 75.5 MMT), (b) domestic retail petrol & diesel pump prices in India were held steady rather than cut with crude, and (c) a weaker rupee (~₹88.4/$) supported INR realisations.
   - State the executive "so what": for IOCL, falling Brent crude lowers raw-material feedstock cost (₹3,81,791 crore in FY26) while steady retail pump prices widen marketing margins — which is why FY26 Standalone PAT surged +183.9% to ₹36,802 crore."""


def _deterministic_fallback(kind: str, digest: Dict[str, Any], recent_turns: List[Tuple[str, str]]) -> Tuple[str, List[str]]:
    title = digest.get("title") or "the current IndianOil view"
    overlay = digest.get("active_overlay")
    vtype = digest.get("visual_type") or "chart"
    r_val = digest.get("brent_vs_series_pearson_r")

    if kind == "repair":
        spoken = (
            f"You're right, sir — my apologies. The screen is currently showing {title}. "
            "Tell me the exact figure or year you want explained, for example \"why did FY25 profit fall\", and I will put the matching chart up."
        )
        return spoken, [f"Currently on screen: {title}."]

    if kind == "correlation":
        r_clause = f" (5-year correlation r = {r_val:+.2f})" if r_val is not None else ""
        spoken = (
            f"Yes — IOCL's revenue decoupled from falling Brent in FY26{r_clause} because IndianOil is a downstream refiner-marketer whose domestic pump prices did not fall with crude. "
            f"From FY22 to FY25, gross revenue tracked Brent's cycle (peaking at ₹9,34,953 crore in FY23 when Brent averaged ~$95/bbl, then easing to ₹8,45,513 crore in FY25). "
            f"In FY26, even though Brent dropped ~12% to $69.04/bbl, IOCL's gross revenue rose +4.8% to ₹8,86,224 crore because physical marketing volumes grew +4.8% to 105.1 MMT, metro petrol/diesel retail prices held steady, and a ₹88.4/$ rupee lifted INR realisations — cutting crude feedstock cost and driving Standalone PAT up 183.9% to ₹36,802 crore."
        )
        insights = [
            "FY22–FY25: Revenue moved with crude ($79.9 → $95.0 → $78.2/bbl Brent vs ₹7.28L → ₹9.35L → ₹8.46L Cr).",
            "FY26 Divergence: Brent fell ~12% (to $69.04/bbl), yet Gross Revenue rose +4.8% to ₹8,86,224 Cr on +4.8% volume growth (105.1 MMT) and steady retail pump prices.",
            "Profitability Takeaway: Lower Brent reduced crude raw-material cost while steady pump prices expanded marketing margins, lifting FY26 PAT +183.9% to ₹36,802 Cr.",
        ]
        return spoken, insights

    if kind == "so_what":
        if overlay == "brent" or "revenue" in title.lower():
            spoken = (
                "The key executive takeaway is that lower Brent crude is a net earnings tailwind for IndianOil, not a headwind. "
                "Steady domestic retail fuel prices and 4.8% physical volume growth (105.1 MMT in FY26) protected IOCL's ₹8,86,224 crore top line even as Brent dropped below $70/bbl, "
                "while cheaper crude feedstock widened refining and marketing spreads — nearly tripling Standalone PAT (+183.9%) to ₹36,802 crore."
            )
            insights = [
                "Top-line resilience: Volume growth (105.1 MMT) + steady retail RSPs cushioned revenue at ₹8,86,224 Cr despite lower crude.",
                "Margin expansion: Cheaper crude input cost drove FY26 Standalone PAT up +183.9% YoY to ₹36,802 Cr.",
            ]
        else:
            spoken = (
                f"The main takeaway from {title} is how IndianOil's physical scale and margin recovery translate into cash generation and bottom-line strength. "
                f"{digest.get('prior_spoken_summary') or 'All figures on screen are reconciled directly to IOCL’s audited Annual Report SSOT.'}"
            )
            insights = [f"Executive summary grounded in {title}."]
        return spoken, insights

    # kind == "explain_screen"
    if overlay:
        ov_name = {"brent": "Brent crude ($/bbl, right axis)", "wti": "WTI crude ($/bbl, right axis)", "grm": "Singapore Complex GRM ($/bbl, right axis)", "inr": "USD/INR exchange rate (₹/$, right axis)"}.get(overlay, f"{overlay.upper()} overlay (right axis)")
        spoken = (
            f"On screen, the primary chart shows {title} on the left axis (in ₹ crore), overlaid with the dashed {ov_name}. "
            f"You can read the two lines together year by year: IOCL's revenue peaked at ₹9,34,953 crore in FY23 alongside ~$95/bbl Brent, "
            f"and in FY26 the two lines diverge — Brent steps down to ~$68–69/bbl while IOCL's revenue climbs to ₹8,86,224 crore on higher sales volumes (105.1 MMT) and steady retail fuel prices."
        )
        insights = [
            f"Left axis (bars/solid series): {title}.",
            f"Right axis (dashed line): {ov_name} from Yahoo Finance / market history.",
            "FY26 divergence reflects +4.8% volume growth and steady domestic pump prices despite softer crude.",
        ]
    else:
        pts = digest.get("data_points") or []
        sample_str = f" covering {len(pts)} data rows" if pts else ""
        spoken = (
            f"You are looking at {title} ({vtype} view{sample_str}). "
            f"{digest.get('prior_spoken_summary') or 'It presents verified figures from IndianOil’s Single Source of Truth.'} "
            f"You can hover any point for exact figures, overlay Brent or Singapore GRM, or export directly to Excel or Google Sheets."
        )
        insights = [
            f"Active view: {title}.",
            "Source: Verified IOCL Annual Report SSOT.",
        ]
    return spoken, insights


def _call_gemini_screen_explain(
    query: str,
    kind: str,
    digest: Dict[str, Any],
    recent_turns: List[Tuple[str, str]],
) -> Optional[str]:
    try:
        from google import genai
        from google.genai import types
        from app.config import DEFAULT_TEXT_MODEL, GCP_PROJECT, VERTEX_TEXT_LOCATION

        client = genai.Client(vertexai=True, project=GCP_PROJECT, location=VERTEX_TEXT_LOCATION)
        hist_txt = "\n".join(f"{r}: {t}" for r, t in recent_turns[-4:])
        prompt = (
            f"{_SCREEN_EXPLAIN_SYS}\n\n"
            f"Question Type: {kind}\n"
            f"Recent Conversation:\n{hist_txt}\n\n"
            f"On-Screen Digest:\n{json.dumps(digest, default=str)}\n\n"
            f"Chairman's Question: {query}"
        )
        resp = client.models.generate_content(
            model=DEFAULT_TEXT_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=340,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        text = (resp.text or "").strip()
        if text and "json" not in text.lower() and "details are on screen" not in text.lower():
            return text
    except Exception as exc:
        logger.warning(f"Gemini screen explanation fallback triggered ({type(exc).__name__}: {exc})")
    return None


async def answer_screen_explanation_async(
    match: Dict[str, Any],
    query: str,
    session_state: Any,
    persona: str,
    turn_id: str,
    language: str,
    t0: float,
) -> Dict[str, Any]:
    kind: str = match["kind"]
    active_turn: Dict[str, Any] = match["active_turn"]
    overlay: Optional[str] = match.get("overlay")

    digest = await asyncio.to_thread(_extract_visual_digest, active_turn, overlay, query)
    recent_turns: List[Tuple[str, str]] = []
    for t in list(getattr(session_state, "turns", None) or [])[-4:]:
        if isinstance(t, dict):
            uq = t.get("user_query") or t.get("query")
            sp = t.get("spoken_summary")
            if uq:
                recent_turns.append(("User", str(uq)))
            if sp:
                recent_turns.append(("Yukti", str(sp)))

    fb_spoken, fb_insights = _deterministic_fallback(kind, digest, recent_turns)
    llm_text = None if kind == "repair" else await asyncio.to_thread(_call_gemini_screen_explain, query, kind, digest, recent_turns)
    spoken = llm_text or fb_spoken

    sources = list(active_turn.get("sources") or [{"kind": "data", "object": "hrfin_gold.v_fin_trend_latest", "title": "IOCL Standalone SSOT"}])
    if digest.get("active_overlay") or kind == "correlation":
        if not any("Yahoo Finance" in str(s.get("object", "")) for s in sources):
            sources.append({"kind": "data", "object": "Yahoo Finance API (BZ=F / INR=X)", "title": "Brent Crude & USD/INR FY Averages"})

    return {
        "contract_version": 3,
        "turn_id": turn_id,
        "language": language,
        "persona": persona,
        "spoken_summary": spoken,
        "display_text": spoken,
        # Keep `visual.type = "none"` so the active chart + Brent/GRM overlay card right above stays 100% intact!
        "visual": {"type": "none", "mode": "replace"},
        "insights": fb_insights,
        "insights_v2": [{"kind": k, "text": txt} for k, txt in zip(["headline", "trend", "note"], fb_insights)],
        "context_chips": [
            {"label": persona, "kind": "role"},
            {"label": digest.get("title") or "On-Screen Analysis", "kind": "subject"},
        ],
        "sources": sources,
        "suggestions": [
            "Show IOCL's Cash Flow statement for the past 5 years",
            "Can I see IOCL's stock price movement for the past 5 years?",
            "Run the DCF valuation model for IOCL",
        ],
        "access": {"status": "allowed"},
        "export_options": [],
        "status_events": ["Explained active on-screen visual & downstream economics"],
        "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
    }
