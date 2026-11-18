"""IOCL Finance, Governance, Treasury Hedging, Accounting & MoU Policy Intent Handler.

Handles statutory and internal policy queries (`IOCL-DOA`, `IOCL-HEDGING`,
`IOCL-ACCT`, `IOCL-CAPALLOC`, `IOCL-MOU`) deterministically via `PolicySearchEngine`
with strict zero-HR boundary for Yukti IOCL.
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

from app.tools.policy_search import PolicySearchEngine

_FIN_POLICY_RE = re.compile(
    r"(?:"
    r"\b(?:iocl[-\s]?doa|delegation\s+of\s+(?:financial\s+)?powers?|doa\s+threshold|board\s+finance\s+committee|"
    r"spot\s+crude\s+(?:oil\s+)?(?:cargo\s+)?procurement|crude\s+tender|vlcc\s+charter|refinery\s+turnaround\s+capex|"
    r"maharatna\s+(?:capex|autonomy|mou)|split\s+tendering|proprietary\s+article\s+certificate|"
    r"iocl[-\s]?hedging|hedging\s+policy|crack[-\s]?spread\s+hedg|inventory\s+price\s+protection|"
    r"usd/inr\s+forward\s+cover|cargo[-\s]?in[-\s]?transit|isda\s+counterparty|ind\s+as\s+109|"
    r"iocl[-\s]?acct|ind\s+as\s+115|ind\s+as\s+116|ind\s+as\s+108|section\s+115baa|nrv\s+write[-\s]?down|"
    r"iocl[-\s]?capalloc|hurdle\s+rate|equity\s+irr|stage[-\s]?gate\s+capex|dipam\s+dividend|"
    r"iocl[-\s]?mou|dpe\s+mou|treds|mse\s+procurement)\b"
    r")",
    re.IGNORECASE,
)


def handle_policy(
    query: str,
    session_state: Any,
    norm_persona: str,
    det_lang: str,
    turn_id: str,
    t0: float,
) -> Optional[Dict[str, Any]]:
    """Intercept deterministic IOCL Finance & Governance policy clause lookups."""
    q_clean = re.sub(r"[^\w\s/\-]", " ", (query or "")).strip().lower()
    if not q_clean:
        return None

    # Do not intercept numeric financial statement or refinery table queries
    if re.search(r"\b(rank|top\s+\d+|show\s+the\s+schedule|waterfall|dcf|valuation|what[\s-]if|sensitivity|board\s+note)\b", q_clean):
        return None

    is_policy_ask = bool(_FIN_POLICY_RE.search(query or "")) or (
        ("policy" in q_clean or "clause" in q_clean or "governance" in q_clean or "threshold" in q_clean or "permit" in q_clean)
        and any(
            kw in q_clean
            for kw in (
                "doa",
                "hedg",
                "crack",
                "forex",
                "fx",
                "crude",
                "turnaround",
                "capex",
                "irr",
                "hurdle",
                "dividend",
                "excise",
                "ind as",
                "115baa",
                "mou",
                "dpe",
                "inventory",
                "isda",
            )
        )
    )
    if not is_policy_ask:
        return None

    # Respect RBAC on confidential named ISDA limits / unpublished Board packs for Grade A-D
    from app.access_control import check_access

    acc = check_access(norm_persona, query=query)
    if acc.status == "refused":
        return None

    engine = PolicySearchEngine()
    clauses = engine.search_local(query, top_k=3)
    if not clauses:
        return None

    c0 = clauses[0]
    doc_id = c0.get("doc_id", "IOCL-DOA")
    human_title = c0.get("doc_title") or doc_id
    cref = c0.get("clause_ref", "Clause 1.0")
    ctitle = c0.get("clause_title", "")
    ctext = c0.get("text", "")
    prov = c0.get("provenance", "illustrative")
    prov_label = "verified_ar" if prov == "real" else "illustrative"

    spoken_summary = f"Under {human_title} ({cref} — {ctitle}): {ctext}"
    if len(spoken_summary) > 520:
        spoken_summary = spoken_summary[:517].rstrip() + "..."

    rows = [
        {
            "document": c.get("doc_title") or c.get("doc_id"),
            "doc_id": c.get("doc_id"),
            "clause_ref": c.get("clause_ref"),
            "title": c.get("clause_title"),
            "summary": (c.get("text") or "")[:360],
            "provenance": c.get("provenance", "illustrative"),
        }
        for c in clauses
    ]

    display_lines = [f"**{human_title} — {cref}: {ctitle}**", "", ctext, ""]
    if len(clauses) > 1:
        display_lines.append("**Related Clauses:**")
        for c in clauses[1:]:
            display_lines.append(f"- `{c.get('doc_id')} {c.get('clause_ref')}` — {c.get('clause_title')}: {(c.get('text') or '')[:220]}...")

    lang = det_lang if det_lang in ("en", "hi", "hi-en") else "en"
    sources: List[Dict[str, Any]] = [
        {
            "kind": "policy",
            "doc_id": c.get("doc_id"),
            "clause": c.get("clause_ref"),
            "title": f"{c.get('doc_title') or c.get('doc_id')} ({c.get('clause_ref')})",
            "snippet": (c.get("text") or "")[:240],
            "provenance": c.get("provenance", "illustrative"),
        }
        for c in clauses
    ]

    return {
        "contract_version": 3,
        "turn_id": turn_id,
        "intent": "policy",
        "confidence": "high",
        "language": lang,
        "persona": norm_persona,
        "spoken_summary": spoken_summary,
        "display_text": "\n".join(display_lines),
        "visual": {
            "type": "clause",
            "mode": "replace",
            "title": f"{human_title} — {cref}",
            "subtitle": f"IOCL Finance Policy Corpus · {'Annual Report Note (Real)' if prov == 'real' else 'Illustrative Governance Rule'}",
            "clause": {
                "doc_id": doc_id,
                "doc_title": human_title,
                "clause_ref": cref,
                "clause_title": ctitle,
                "text": ctext,
                "highlight": ctext[:220],
                "provenance": prov,
                "related_clauses": rows[1:],
            },
        },
        "insights": [
            f"{doc_id} · {cref}: {ctext[:280]}"
        ],
        "sources": sources,
        "access": {"status": "allowed"},
        "provenance": {
            "label": prov_label,
            "source_class": "policy_rulebook",
            "detail": f"{human_title} ({cref})",
        },
        "export_options": ["pdf", "docx"],
        "suggestions": [
            "What are the approval limits for spot crude oil cargo procurement under DoA?",
            "What does IOCL Hedging Policy permit for crack spreads and USD/INR forwards?",
            "What is IOCL's post-tax equity IRR hurdle rate for new Capex?",
        ],
        "status_events": [f"Resolved {doc_id} {cref} ({int((time.perf_counter() - t0) * 1000)} ms)"],
    }
