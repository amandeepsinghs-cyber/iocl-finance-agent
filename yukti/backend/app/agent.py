"""Google ADK Agent definition for Yukti AI.
Implements the Yukti persona: brief 2–4 sentence spoken answers,
mirroring user language (en/hi/hi-en), Indian number system, citing sources,
and strictly answering from BigQuery and Vertex AI Search.
"""

import asyncio
import logging
import os
import re
import uuid
from typing import Any, Dict, List, Optional
from google.adk.agents import Agent
from google.genai import types

from app.config import DEFAULT_LIVE_MODEL, DEFAULT_TEXT_MODEL, DEFAULT_VOICE, FALLBACK_LIVE_MODEL
from app.tools.certified_query import run_certified_query as execute_certified_query
from app.tools.draft_document import DocumentDraftingEngine
from app.tools.export_tool import DocumentExporter
from app.tools.policy_search import PolicySearchEngine
from app.tools.query_data import query_data as execute_query_data
from app.tools.semantic_layer import SEMANTIC_LAYER_PROMPT
from app.tools.what_if import run_what_if_simulation

logger = logging.getLogger("yukti.agent")

# Official Yukti System Instructions per approved UX Spec §1, §4, §8, §9, §14
YUKTI_SYSTEM_INSTRUCTION = f"""You are "Yukti", the authoritative voice-first AI agent for Indian Oil Corporation Limited's (IOCL) Chairman and executive leadership.
You deliver instant, grounded intelligence across Corporate Finance, Refining Economics, Pipelines, Marketing, Treasury, and Valuation (`NSE:IOC`).

CORE OPERATIONAL BEHAVIORS:
1. Executive Voice & Persona (UX Spec §9):
   - Deliver brief, punchy spoken summaries (STRICTLY 2 to 3 sentences).
   - NEVER enumerate all rows or all grades verbally. State the overall total count/amount and highlight at most the top 1 or 2 items. Direct the presenter's attention to the interactive canvas chart.
   - Use the EXACT totals and counts provided in the tool's `deterministic_summary`. Never extrapolate or hallucinate numbers from preview rows.
   - Use the Indian numbering system naturally (Lakh, Crore, e.g. "₹36,802.42 Crore", "₹7.84 Lakh Crore", "70.25 MMTPA").
   - Never invent numbers. If data is not available or a query returns 0 rows, state plainly: "Data not available: here is the closest verified information."

2. SPOKEN CITATION RULES (USER DECISION):
   - Spoken answers MUST NEVER mention dataset names, table names, documents, or clause numbers by default. Deliver pure business intelligence.
   - Never say "as verified in hrfin_gold", "according to table ssot_refinery_economics_360", or "Clause 3.0".
   - Sources appear visually ONLY at the bottom of the canvas.
   - Exception: for policy questions, you may mention the policy name naturally ("Under the Delegation of Financial Powers (DoA), ...") but NOT clause numbers unless asked.
   - SOURCE INQUIRIES: Only when the user explicitly asks ("what's the source?", "where is this from?", "kiska data hai?"), speak the source in plain business language (e.g. "This comes from IOCL's FY26 Schedule III published financial statements and refinery economics records."). Never speak database table or view names even then.

3. MANDATORY TOOL USAGE FOR IOCL DATA & METRICS:
   - You MUST call a tool (`run_certified_query`, `query_data`, `search_policy`, `what_if`, or `draft_document`) for EVERY user question inquiring about IOCL data, metrics, refining, pipelines, marketing, policies, finances, or valuation.
   - When the user inquiry matches a certified metric or question (`Q01–Q30`, e.g. Q01 Schedule III P&L, Q07 Refinery GRM ranking, Q13 Balance Sheet, Q20 MoU Scorecard, Q24 WACC), call `run_certified_query(query_id, params)` to execute the verified certified template, supplying parameter overrides as requested (e.g. `fiscal_year`, `from_fy`, `to_fy`).
   - Direct model reasoning without a tool call is STRICTLY FORBIDDEN for any question asking for numbers, metrics, or factual statements.
   - Direct text responses without a tool call are permitted ONLY for greetings (e.g. "hello", "good morning"), conversational pleasantries, and meta questions.
   - TOOL SELECTION RULES:
     * Structured data & metrics (Schedule III P&L/BS/CF, Excise bridge, refinery GRM/throughput, pipeline/marketing sales, segments, MoU, WACC, ratios): call `run_certified_query` or `query_data`.
     * Policies, guidelines, DoA limits, hedging mandates (`IOCL-DOA`, `IOCL-HEDGING`, `IOCL-ACCT`, `IOCL-CAPALLOC`, `IOCL-MOU`): call `search_policy`.
     * What-if simulations (GRM $/bbl shock, USD/INR depreciation, retail auto-fuel margin, throughput): call `what_if`.
     * Drafting official Board Notes, Capex Appraisals, Treasury FX notes, or Parliament replies: call `draft_document`.

3. SQL Generation & Repair Cap:
   - If a SQL query fails syntax validation, attempt at most ONE self-correction. If it fails a second time, report that data is not available.

4. Multilingual & Script Mirroring:
   - Seamlessly converse in English, Hindi, and mixed Hindi-English (Hinglish).
   - Reply in the language and register of the question.

3. Role-Based Access Control:
   - For Officer Grades A–D (`E1_FIN..E4_FIN`), strictly refuse access to confidential counterparty credit sub-ledgers or unpublished Q1 Board draft refinery margin packs (`R-CONF` / `R-FIN`).
   - Deliver polite, brief refusal justifications citing the governing rule, and present authorized public aggregates or policy guidelines.

4. Opening Greeting:
   - When a session initiates, greet the executive:
     "Hello, I am Yukti, your Finance and Downstream Intelligence agent for IndianOil. Please tell me how I can help."
     (In Hindi: "नमस्ते, मैं युक्ति हूँ, इंडियनऑयल की वित्त और डाउनस्ट्रीम सलाहकार। कृपया बताइए मैं आपकी क्या सहायता कर सकती हूँ।")

{SEMANTIC_LAYER_PROMPT}
"""

_POLICY_ENGINE = PolicySearchEngine()
_DRAFT_ENGINE = DocumentDraftingEngine()
_EXPORT_ENGINE = DocumentExporter()


async def query_data(sql_query: str, title: Optional[str] = None) -> Dict[str, Any]:
    """Executes a SELECT query on BigQuery datasets hrfin_gold or hrfin_silver.

    Always follow the 5 Query-Craft rules and dataset allow-list.
    """
    from app.auth import get_active_principal
    from app.brain.rbac import persona_class
    principal = get_active_principal()
    if principal is None:
        return {
            "type": "error",
            "code": "E-AUTH",
            "error": "Authentication error (E-AUTH): no server principal bound for query execution.",
            "retryable": False,
        }
        
    if principal.persona.upper() != "CMD":
        return {
            "status": "refused",
            "error": "Access restricted. Free-form data queries are not available for your role (D-64).",
            "sql": sql_query,
            "chart_kind": "refusal",
            "code": "R-FUNC"
        }
    return await asyncio.to_thread(
        execute_query_data, 
        sql_query=sql_query, 
        title=title, 
        persona=principal.persona
    )


async def run_certified_query(
    query_id: str,
    params: Optional[Dict[str, Any]] = None,
    wc_id: Optional[str] = None,
    fiscal_year: Optional[str] = None,
    min_stay_days: Optional[int] = None,
    min_grade: Optional[str] = None,
    field_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Executes a certified parameterized query template from the verified query library.
    ALWAYS prefer calling `run_certified_query` first before `query_data` for standard questions:
    - 'Q01': Schedule III Profit and Loss statement & Excise bridge (fiscal_year='FY26')
    - 'Q07': Refinery-wise GRM ($/bbl) and EBITDA ranking across 9 refineries (fiscal_year='FY26')
    - 'Q11': Domestic petroleum product marketing volume breakdown (MS, HSD, ATF, LPG)
    - 'Q13': Schedule III Balance Sheet & Solvency (fiscal_year='FY26')
    - 'Q17': Ind-AS 7 Cash Flow Statement & Free Cash Flow waterfall
    - 'Q20': DPE / MoPNG Maharatna MoU scorecard vs targets
    - 'Q24': IOC.NS WACC attribution bridge (FY22-FY26)
    - 'Q26': NSE:IOC DCF valuation inputs anchor
    """
    merged: Dict[str, Any] = dict(params or {})
    if wc_id:
        merged["wc_id"] = wc_id
    if fiscal_year:
        merged["fiscal_year"] = fiscal_year
    if min_stay_days is not None:
        merged["min_stay_days"] = min_stay_days
    if min_grade:
        merged["min_grade"] = min_grade
    if field_id:
        merged["field_id"] = field_id
    from app.auth import get_active_principal

    principal = get_active_principal()
    if principal is None:
        return {
            "type": "error",
            "code": "E-AUTH",
            "error": "Authentication error (E-AUTH): no server principal bound for certified query execution.",
            "retryable": False,
        }
    return await asyncio.to_thread(
        execute_certified_query,
        query_id=query_id,
        params=merged or None,
        persona=principal.persona,
        self_emp_id=principal.emp_id,
    )


async def search_policy(query: str) -> Dict[str, Any]:
    """Searches official IOCL Finance, DoA, Hedging, Accounting, and MoU policy clauses."""
    return await asyncio.to_thread(_POLICY_ENGINE.search, query=query)


async def what_if(
    scenario: str,
    brent_price: Optional[float] = 60.0,
    freeze_months: Optional[int] = 24,
    relocated_officers: Optional[int] = 200,
    cta_lakh: Optional[float] = 3.25,
) -> Dict[str, Any]:
    """Runs a live parameterized what-if simulation on BigQuery:

    - scenario='grm_shock': refinery GRM $/bbl uplift/compression across 75.45 MMT
    - scenario='fx_shock': USD/INR exchange rate sensitivity on crude imports & debt
    - scenario='retail_margin': MS/HSD marketing margin ₹/litre sensitivity
    - scenario='brent_price': crude & inventory valuation sensitivity
    """
    return await asyncio.to_thread(
        run_what_if_simulation,
        scenario=scenario,
        brent_price=brent_price,
        freeze_months=freeze_months,
        relocated_officers=relocated_officers,
        cta_lakh=cta_lakh,
    )


async def draft_document(
    doc_type: str,
    topic: str,
    instruction: Optional[str] = None,
    version: int = 1,
) -> Dict[str, Any]:
    """Drafts or revises an official IOCL Board Note, Capex Appraisal, Treasury FX Note, or Parliament Reply.

    Supports instruction='make it shorter', 'add GRM +$1.50/bbl scenario', 'translate to Hindi'.
    """
    return await asyncio.to_thread(
        _DRAFT_ENGINE.draft,
        doc_type=doc_type,
        query=topic,
        version=version,
        instruction=instruction,
    )


def _export_document_sync(format: str, title: str, content: str) -> Dict[str, Any]:
    fmt = format.lower()
    # H1.3a: the title comes from the model — never use it as a raw path (DocumentExporter.safe_path also guards)
    title = re.sub(r"[^A-Za-z0-9_\-]", "_", str(title or "Yukti_Export"))[:80] or "Yukti_Export"
    export_id = f"exp_{uuid.uuid4().hex}"  # minted id: no cross-user overwrite, no server path back to the model
    if "word" in fmt or "docx" in fmt:
        _EXPORT_ENGINE.export_word(markdown_text=content, filename=f"{export_id}.docx")
        return {"status": "success", "export_id": export_id, "filename": f"{title}.docx", "format": "docx"}
    elif "pdf" in fmt:
        _EXPORT_ENGINE.export_pdf(markdown_text=content, filename=f"{export_id}.pdf")
        return {"status": "success", "export_id": export_id, "filename": f"{title}.pdf", "format": "pdf"}
    elif "doc" in fmt:
        res = _EXPORT_ENGINE.export_google_docs(title=title, markdown_text=content, file_id=export_id)
        return {"status": "success", "export_id": export_id, "filename": f"{title}.docx", "format": "docs", "url": res.get("url")}
    return {"status": "success", "format": fmt}


async def export_document(format: str, title: str, content: str) -> Dict[str, Any]:
    """Exports documents or tabular statements to Word (.docx), Excel (.xlsx), PDF, or Google Docs/Sheets."""
    return await asyncio.to_thread(_export_document_sync, format, title, content)


def create_yukti_agent(
    model_name: Optional[str] = None,
    instruction_override: Optional[str] = None,
    principal: Optional[Any] = None,
) -> Agent:
    """Instantiates the Google ADK Agent for Yukti AI with minimal thinking overhead."""
    active_model = model_name or os.getenv("YUKTI_TEXT_MODEL", DEFAULT_TEXT_MODEL)
    instruction = instruction_override or YUKTI_SYSTEM_INSTRUCTION

    # Optimize thinking budget for text models only (live audio models do not customize thinking level)
    if "live" not in active_model.lower():
        if "3." in active_model or "3-" in active_model:
            gen_cfg = types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_level="low")
            )
        else:
            gen_cfg = types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0)
            )
    else:
        gen_cfg = None

    from app.auth import get_active_principal
    from app.brain.rbac import persona_class
    principal = principal or get_active_principal()
    pc = persona_class(principal.persona) if principal else "junior"
    
    # D-64: Juniors get no free-form SQL tool
    tools = [
        run_certified_query,
        search_policy,
        what_if,
        draft_document,
        export_document,
    ]
    if principal and principal.persona.upper() == "CMD":
        tools.append(query_data)

    return Agent(
        name="yukti_ai_agent",
        model=active_model,
        instruction=instruction,
        generate_content_config=gen_cfg,
        tools=tools,
    )
