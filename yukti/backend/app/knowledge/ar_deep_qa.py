"""Universal Open-Ended Annual Report Deep-QA route (`IOCL-R04`).

Retrieves verbatim passages across IOCL's 10 Annual Reports (`FY17–FY26`, 8,437 embedded chunks
in `hrfin_docs.doc_chunks_ar` + `financial_notes_chunks` / local fallback when offline) and
synthesizes a crisp 2-4 sentence executive briefing citing `[AR FYxx p.NN]`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.config import DEFAULT_TEXT_MODEL, GCP_PROJECT, VERTEX_TEXT_LOCATION
from app.knowledge.ar_retriever import ARRetriever, citation as ar_citation, query_terms
from app.semantic.normalize import resolve_fy

logger = logging.getLogger("yukti.knowledge.ar_deep_qa")

_AR_DIRECT_RE = re.compile(
    r"\b("
    r"annual\s+reports?|ar\s+fy\d{2}|disclosur\w*|footnotes?|note\s+\d+|"
    r"contingent\s+liabilit\w*|capital\s+commitments?|related\s+part\w*|"
    r"c&ag|comptroller|auditor['’]?s?\s+report|statutory\s+auditors?|caro\b|"
    r"panipat\s+p-?25|barauni\s+br-?9|paradip\s+petchem|koyali\s+expan\w*|"
    r"green\s+hydrogen|net[- ]?zero\s*(?:2046)?|energy\s+transition|"
    r"r&d\s+(?:spend|expenditure|activit\w*)|research\s+and\s+development|"
    r"csr\s+(?:spend|projects?|activit\w*)|corporate\s+social\s+responsibility|"
    r"ind\s*as\s*\d+|lease\s+commitments?|litigation|claims?\s+against\s+the\s+company|"
    r"guarantees?|md&a|management\s+discussion|director['’]?s?\s+report|"
    r"chairman['’]?s?\s+(?:statement|speech|address)|corporate\s+governance"
    r")\b",
    re.I,
)
# Exclude turns that already belong to structured SSOT tables, variance attribution, DCF, or smalltalk
_EXCLUDE_DIRECT_RE = re.compile(
    r"\b("
    r"why\s+did\b|what\s+drove\b|what\s+caused\b|run\s+(?:a\s+)?dcf|"
    r"p&l\s+statement|income\s+statement|balance\s+sheet|cash\s+flow\s+statement|"
    r"total\s+cash\s+flows?|cash\s+flow\s+trend|cash\s+flows?\s+(?:for|over)\s+(?:the\s+)?(?:past|last)|"
    r"which\s+screen|still\s+seeing|stock\s*(?:market\s*|mrket\s*)?prices?|share\s+prices?|market\s+price\s+of|"
    r"financial\s+ratios|mou\s+scorecard|wacc\b|top\s*5\s*(?:actions|levers)|"
    r"petrol|diesel|hsd|lpg|atf|brent|wti|what\s+can\s+you\s+do"
    r")\b",
    re.I,
)
_GREETING_ONLY_RE = re.compile(
    r"^\s*(hi|hello|hey|namaste|good\s+(morning|afternoon|evening)|how\s+are\s+you|"
    r"thanks|thank\s+you|bye|goodbye|who\s+are\s+you|what\s+can\s+you\s+do|help)\b[?!.\s]*$",
    re.I,
)

_SYNTH_SYS = """You are Yukti, the executive Finance & Downstream Intelligence assistant for Indian Oil Corporation Limited (IOCL).
Answer the user's question in 2-4 crisp, boardroom-register sentences grounded STRICTLY in the verbatim Annual Report excerpts below.
Rules:
- Cite inline using the exact [AR FYxx p.NN] tags attached to the excerpts you rely on.
- Use ₹ and Indian digit grouping where quoting amounts from the excerpts; NEVER invent numbers or facts not present in the excerpts.
- Never refer to "JSON", "payload", "chunks", or "provided context". Speak directly about IOCL's Annual Report disclosures.
- Never claim that data is "not available", "not a continuous series", or "only for select periods": Yukti holds a verified
  FY17–FY26 financial SSOT. If the excerpts don't contain a figure, simply answer with what they do contain.
- If the question is in Hindi (`language=hi`), respond in Devanagari Hindi; otherwise Indian English. Plain text only."""


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for d in (4, 3, 5):
        if len(here.parents) > d and (here.parents[d] / "financial_build").exists():
            return here.parents[d]
    return here.parents[min(4, len(here.parents) - 1)]


@lru_cache(maxsize=1)
def _load_local_ar_corpus() -> List[Dict[str, Any]]:
    root = _repo_root()
    rows: List[Dict[str, Any]] = []
    for p, fmt in (
        (root / "financial_ssot" / "out" / "doc_chunks_ar.jsonl", "ar"),
        (root / "financial_build" / "data" / "financial_notes_corpus.jsonl", "notes"),
    ):
        if not p.exists():
            continue
        with p.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if fmt == "ar":
                    rows.append({
                        "chunk_id": obj.get("chunk_id") or "",
                        "fiscal_year": obj.get("fiscal_year") or "FY26",
                        "source_doc": obj.get("source_doc") or "",
                        "source_page": obj.get("source_page"),
                        "source_page_label": obj.get("source_page_label"),
                        "section": obj.get("section") or "notes",
                        "note_no": obj.get("note_no") or "",
                        "heading": obj.get("heading") or "",
                        "text": obj.get("text") or "",
                    })
                else:
                    rows.append({
                        "chunk_id": obj.get("chunk_id") or "",
                        "fiscal_year": obj.get("fy") or "FY26",
                        "source_doc": f"IOCL_AR_{obj.get('fy', 'FY26')}.pdf",
                        "source_page": None,
                        "source_page_label": obj.get("note_ref") or None,
                        "section": obj.get("statement_type") or "notes",
                        "note_no": obj.get("note_ref") or "",
                        "heading": obj.get("title") or "",
                        "text": obj.get("content") or "",
                    })
    return rows


def _extract_fy(query: str) -> Optional[str]:
    res = resolve_fy(query or "")
    if isinstance(res, dict) and res.get("fy"):
        return str(res["fy"]).upper()
    m = re.search(r"\b(FY\s?\d{2})\b", query or "", re.I)
    if m:
        return m.group(1).replace(" ", "").upper()
    m2 = re.search(r"\b(201[7-9]|202[0-6])\b", query or "")
    if m2:
        return f"FY{int(m2.group(1)) % 100:02d}"
    return None


def _extract_note_no(query: str) -> Optional[str]:
    m = re.search(r"\bnote\s+(\d+[A-Za-z]?)\b", query or "", re.I)
    return m.group(1).lower() if m else None


def detect_ar_deep_qa(query: str) -> Optional[Dict[str, Any]]:
    """Direct trigger for explicit Annual Report disclosure / note / project questions."""
    q = (query or "").strip()
    if not q or _GREETING_ONLY_RE.match(q) or _EXCLUDE_DIRECT_RE.search(q):
        return None
    if _AR_DIRECT_RE.search(q):
        return {"kind": "ar_deep_qa", "fy": _extract_fy(q), "note_no": _extract_note_no(q)}
    return None


_CONVERSATIONAL_FILLER_RE = re.compile(
    r"^\s*(?:"
    r"all\s+right|alright|got\s+it|sounds\s+good|okay|ok|sure|fine|great|cool|nice|"
    r"thank(?:s|\s+you)|yes|yeah|yep|no|nope|cancel|hi|hello|hey|bye|goodbye|"
    r"i'?ll\s+do|let\s+me|one\s+(?:sec|second|moment)|hold\s+on|wait|never\s*mind|sorry|"
    r"good\s+job|well\s+done|awesome|perfect"
    r")\b",
    re.I,
)

_SUBSTANTIVE_AR_DOMAIN_RE = re.compile(
    r"\b(?:"
    r"iocl|indianoil|indian\s+oil|cpcl|lanka\s+ioc|petronet|ongc|oil\s+india|"
    r"annual\s+report|disclosure|footnote|note\s+\d+|schedule\s+(?:iii|3)|ind\s*as|"
    r"contingent|liabilit\w*|commitment\w*|litigation|arbitration|claim\w*|guarantee\w*|"
    r"auditor|c&ag|caro|governance|board|director|dividend|equity|reserve\w*|borrow\w*|debt|lease\w*|"
    r"refiner\w*|panipat|paradip|koyali|mathura|haldia|barauni|guwahati|digboi|bongaigaon|"
    r"pipeline\w*|petchem|petrochemical|lpg|indane|atf|lube|servo|ethanol|biofuel|hydrogen|solar|wind|ev\b|net[- ]?zero|esg|csr|r&d|research|"
    r"subsidiar\w*|joint\s+venture|\bjv\b|associate\w*|capex|project\w*|expansion|capacity|throughput|grm|margin|inventory|impairment|tax|excise|vat|segment|revenue|profit|ebitda|cash\s+flow|balance\s+sheet"
    r")\b",
    re.I,
)


def should_fallback_to_ar(query: str) -> bool:
    """Only consult the 10-year AR corpus on unresolved turns that carry a real IOCL/finance/disclosure signal."""
    q = (query or "").strip()
    if not q or len(q.split()) < 3 or _GREETING_ONLY_RE.match(q) or _CONVERSATIONAL_FILLER_RE.match(q):
        return False
    from app.brain.explain_screen import is_repair_or_meta_question

    if is_repair_or_meta_question(q):
        return False
    from app.market.oil_intent import detect_stock_price_plot

    if detect_stock_price_plot(q) is not None:
        return False
    return bool(_SUBSTANTIVE_AR_DOMAIN_RE.search(q))


def _is_garbled_ocr(text: str) -> bool:
    """Detect corrupted custom-font PDF extractions (e.g. FY19 '4HE #OMPANY', 'TOKEEPYOURPASSWORDCONlDENTIAL')."""
    s = str(text or "")
    if not s:
        return True
    sample = s[:500]
    # Corrupted font shift: punctuation/digits embedded directly before uppercase runs like ')NDIAN', '4HE', '#OMPANY', '3HRI0ARINDU'
    if len(re.findall(r"[0-9#()\"'/\\][A-Z]{2,}", sample)) >= 2:
        return True
    # Spaceless long uppercase runs (e.g. TOKEEPYOURPASSWORDCONlDENTIAL, ONSUCCESSFULLOGIN)
    if len(re.findall(r"[A-Z]{18,}", sample)) >= 1:
        return True
    if len(_SPACED_OCR_RE.findall(sample)) >= 3:
        return True
    return False


def _trim_to_sentence(text: str) -> str:
    """Avoid mid-word truncation if a completion hits token limit."""
    s = (text or "").strip()
    if not s or s[-1] in ".!?\"'”)]":
        return s
    # Trim back to the last clean sentence boundary if present past 40% of the string
    m = re.search(r"^(.*[.!?])(?:\s+[^.!?]*)$", s, re.S)
    if m and len(m.group(1)) >= max(60, int(len(s) * 0.4)):
        return m.group(1).strip()
    return s.rstrip(",;:- ") + "."


_LEXICAL_STOPWORDS = {
    "the", "and", "for", "from", "with", "what", "when", "where", "which", "who", "how",
    "are", "was", "were", "did", "does", "have", "has", "had", "into", "that", "this",
    "tell", "about", "show", "give", "major", "key", "iocl", "indianoil", "indian", "oil",
    "annual", "report", "reports", "disclosed", "disclosure", "disclosures", "target",
    "targets", "expansion", "initiatives", "mentioned", "stated",
}
_SPACED_OCR_RE = re.compile(r"\b[A-Za-z]\s+[A-Za-z]\s+[A-Za-z]\b")


def _lexical_fallback_retrieve(query: str, fy: Optional[str], top_k: int = 8) -> List[Dict[str, Any]]:
    corpus = _load_local_ar_corpus()
    if not corpus:
        return []
    q_low = (query or "").lower()
    terms = [t for t in query_terms(query) if t not in _LEXICAL_STOPWORDS]
    raw_tokens = {
        t.lower()
        for t in re.findall(r"[A-Za-z0-9&-]{3,}", query or "")
        if t.lower() not in _LEXICAL_STOPWORDS and not re.fullmatch(r"fy\d{2}|20\d{2}", t, re.I)
    }
    phrases = [
        p for p in (
            "contingent liabilities", "capital commitments", "related party",
            "net-zero", "net zero", "green hydrogen", "panipat", "p-25",
            "statutory auditor", "r&d", "research and development", "csr",
        )
        if p in q_low
    ]
    note_req = _extract_note_no(query)
    scored: List[tuple[float, Dict[str, Any]]] = []
    for c in corpus:
        raw_txt = str(c.get("text") or "")
        txt_l = f"{c.get('heading', '')} {c.get('note_no', '')} {raw_txt}".lower()
        score = 0.0
        for t in terms:
            if t in txt_l:
                score += 2.0
        for t in raw_tokens:
            if t in txt_l:
                score += 1.0
        for ph in phrases:
            if ph in txt_l:
                score += 5.0
        if fy and str(c.get("fiscal_year") or "").upper() == fy:
            score += 3.0
        if note_req and f"note {note_req}" in f"{c.get('note_no', '')} {c.get('heading', '')} {txt_l}".lower():
            score += 6.0
        if "r&d" in q_low and ("research" in txt_l or "r&d" in txt_l):
            score += 4.0
        if "contingent" in q_low and "contingent" in txt_l:
            score += 4.0
        if len(_SPACED_OCR_RE.findall(raw_txt[:300])) >= 2:
            score -= 5.0
        if score >= 3.0:
            item = dict(c)
            item["citation"] = ar_citation(item)
            item["provenance_label"] = "verified_ar"
            scored.append((score, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [it for _, it in scored[:top_k]]


def retrieve_ar_chunks(
    query: str,
    fiscal_year: Optional[str] = None,
    top_k: int = 8,
    retriever: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Query BigQuery `hrfin_docs.doc_chunks_ar` via `ARRetriever`, falling back to local AR corpus offline."""
    chunks: List[Dict[str, Any]] = []
    try:
        ar = retriever if retriever is not None else ARRetriever()
        chunks = ar.retrieve(query, fiscal_year=fiscal_year, top_k=top_k) or []
        if not chunks and fiscal_year is not None and retriever is None:
            chunks = ar.retrieve(query, fiscal_year=None, top_k=top_k) or []
    except Exception as exc:
        logger.info(f"ARRetriever live BQ unavailable ({type(exc).__name__}: {exc}); using local AR corpus fallback")
    if not chunks:
        chunks = _lexical_fallback_retrieve(query, fiscal_year, top_k=top_k)
        if not chunks and fiscal_year is not None:
            chunks = _lexical_fallback_retrieve(query, None, top_k=top_k)
    clean_chunks = [c for c in chunks if not _is_garbled_ocr(c.get("text") or "")]
    return clean_chunks if clean_chunks else chunks


def _synthesize_with_gemini(query: str, chunks: List[Dict[str, Any]], language: str) -> Optional[str]:
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(vertexai=True, project=GCP_PROJECT, location=VERTEX_TEXT_LOCATION)
        excerpts = "\n\n".join(
            f"{c.get('citation') or ar_citation(c)} ({c.get('section') or 'AR'} | {c.get('heading') or c.get('note_no') or ''}):\n"
            f"{str(c.get('text') or '')[:900]}"
            for c in chunks[:6]
        )
        prompt = f"{_SYNTH_SYS}\n\nlanguage={language}\nQuestion: {query}\n\nExcerpts:\n{excerpts}"
        resp = client.models.generate_content(
            model=DEFAULT_TEXT_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.15,
                max_output_tokens=512,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        txt = _trim_to_sentence(resp.text or "")
        return txt or None
    except Exception as exc:
        logger.info(f"AR Deep-QA Gemini synthesis fallback ({type(exc).__name__}: {exc})")
        return None


def _clean_snippet(text: str, max_len: int = 260) -> str:
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(s) <= max_len:
        return s
    cut = s[:max_len].rsplit(" ", 1)[0]
    return (cut or s[:max_len]) + "..."


def _deterministic_summary(chunks: List[Dict[str, Any]]) -> str:
    top = chunks[0]
    cit1 = top.get("citation") or ar_citation(top)
    head1 = str(top.get("heading") or top.get("note_no") or "Annual Report disclosure").strip()
    snip1 = _clean_snippet(top.get("text") or "", 220)
    parts = [f"Per IOCL {cit1} ({head1}): {snip1}"]
    if len(chunks) > 1:
        c2 = chunks[1]
        cit2 = c2.get("citation") or ar_citation(c2)
        if cit2 != cit1:
            parts.append(f"Additional disclosure in {cit2}: {_clean_snippet(c2.get('text') or '', 150)}")
    return " ".join(parts)


def make_spoken(text: str, max_sentences: int = 2, max_words: int = 55) -> str:
    """R5 (plan_fix.md): voice-friendly version — strip [AR FYxx p.NN] tags, keep ≤2 sentences / ~55 words."""
    s = re.sub(r"\s*\[(?:AR\s+)?FY\d{2}[^\]]*\]", "", text or "")
    s = re.sub(r"\s{2,}", " ", s).strip()
    sents = [x.strip() for x in re.split(r"(?<=[.!?।])\s+", s) if x.strip()]
    out: List[str] = []
    words = 0
    for x in sents[:max_sentences]:
        n = len(x.split())
        if out and words + n > max_words:
            break
        out.append(x)
        words += n
    return " ".join(out) if out else s


def answer_ar_deep_qa(
    query: str,
    persona: str,
    turn_id: str,
    language: str,
    t0: float,
    *,
    retriever: Optional[Any] = None,
    synth_fn: Optional[Callable[[str, List[Dict[str, Any]], str], Optional[str]]] = None,
    fiscal_year: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    fy = fiscal_year or _extract_fy(query)
    chunks = retrieve_ar_chunks(query, fiscal_year=fy, top_k=8, retriever=retriever)
    if not chunks:
        return None

    synth = synth_fn or _synthesize_with_gemini
    answer = synth(query, chunks, language) or _deterministic_summary(chunks)

    table_rows: List[Dict[str, Any]] = []
    sources: List[Dict[str, Any]] = []
    seen_src = set()
    for c in chunks[:5]:
        cit = c.get("citation") or ar_citation(c)
        fy_c = str(c.get("fiscal_year") or fy or "FY26")
        sec = str(c.get("note_no") or c.get("heading") or c.get("section") or "Annual Report").strip()
        table_rows.append({
            "fiscal_year": fy_c,
            "section": sec[:80],
            "citation": cit,
            "key_disclosure": _clean_snippet(c.get("text") or "", 280),
        })
        doc = str(c.get("source_doc") or f"IOCL_AR_{fy_c}.pdf")
        pg = c.get("source_page_label") or c.get("source_page")
        src_key = (doc, str(pg))
        if src_key not in seen_src:
            seen_src.add(src_key)
            sources.append({
                "kind": "document",
                "object": doc,
                "title": f"IOCL Annual Report {fy_c}" + (f" p.{pg}" if pg else ""),
            })

    top = chunks[0]
    top_cit = top.get("citation") or ar_citation(top)
    insights = [
        f"Top Annual Report match: {top_cit} — {str(top.get('heading') or top.get('note_no') or top.get('section') or 'Disclosure')[:90]}.",
        f"Grounded across {len(sources)} cited IOCL Annual Report source(s) covering FY17–FY26.",
    ]

    return {
        "turn_id": turn_id,
        "language": language,
        "persona": persona,
        "spoken_summary": make_spoken(answer),
        "display_text": answer,
        "visual": {
            "type": "table",
            "mode": "replace",
            "title": "IOCL Annual Report Disclosures & Citations",
            "subtitle": f"{len(table_rows)} verbatim Annual Report excerpts · {top_cit}",
            "table": {
                "columns": ["fiscal_year", "section", "citation", "key_disclosure"],
                "rows": table_rows,
                "total_rows": len(table_rows),
                "masking": {"level": "none"},
            },
        },
        "insights": insights,
        "insights_v2": [{"kind": "note", "text": s} for s in insights],
        "context_chips": [
            {"label": persona, "kind": "role"},
            {"label": fy or "FY17–FY26 AR", "kind": "period"},
            {"label": top_cit, "kind": "source"},
        ],
        "sources": sources,
        "provenance": {
            "label": "verified_ar",
            "badge": "AR-cited",
            "doc": str(top.get("source_doc") or ""),
            "page_label": str(top.get("source_page_label") or top.get("source_page") or ""),
        },
        "suggestions": [
            "Show IOCL's P&L statement for FY26",
            "What is IOCL's Balance Sheet for FY26?",
            "Show IOCL capex trend from FY17 to FY26",
        ],
        "access": {"status": "allowed"},
        "export_options": ["pdf", "xlsx"],
        "status_events": [f"Retrieved {len(chunks)} Annual Report chunks ({top_cit})"],
        "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
    }


async def answer_ar_deep_qa_async(
    query: str,
    persona: str,
    turn_id: str,
    language: str,
    t0: float,
    *,
    retriever: Optional[Any] = None,
    synth_fn: Optional[Callable[[str, List[Dict[str, Any]], str], Optional[str]]] = None,
    fiscal_year: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    return await asyncio.to_thread(
        answer_ar_deep_qa,
        query,
        persona,
        turn_id,
        language,
        t0,
        retriever=retriever,
        synth_fn=synth_fn,
        fiscal_year=fiscal_year,
    )
