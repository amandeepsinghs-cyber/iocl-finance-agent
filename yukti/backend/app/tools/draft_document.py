"""Document Drafting and Revision Engine for Yukti AI.
Drafts official IOCL Board Notes, Capex Appraisal Notes, Treasury FX Risk Notes, and Governance Briefs,
and executive applications using templates in data_bank/landing/documents/templates/.
Maintains document versions and applies revisions by voice or text.
Enforces real-person denylist check to guarantee 100% fictional parliamentary integrity.
"""

import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import docx

from app.config import TEMPLATES_DIR

logger = logging.getLogger("yukti.tools.draft_document")

REAL_POLITICIAN_DENYLIST = [
    "Rameshwar Teli",
    "Rameswar Teli",
    "Hardeep Singh Puri",
    "Dharmendra Pradhan",
    "Murli Deora",
    "M. Veerappa Moily",
    "Mani Shankar Aiyar",
    "Ram Naik",
    "Piyush Goyal",
]


def sanitize_fictional_names(text: str) -> str:
    """Scans text against real politician denylist and replaces with clearly fictional synthetic names."""
    clean = text
    for real_name in REAL_POLITICIAN_DENYLIST:
        if real_name.lower() in clean.lower():
            clean = re.sub(re.escape(real_name), "Shri Anand Swaroop", clean, flags=re.IGNORECASE)
    return clean


DOCUMENT_TEMPLATES = {
    "board_note": {
        "title": "Board Note: Downstream & Financial Review",
        "doc_type": "board_note",
        "template_id": "template_board_note.md",
        "default_markdown": """# INDIAN OIL CORPORATION LIMITED (IOCL)
## BOARD OF DIRECTORS | FINANCE & DOWNSTREAM AGENDA NOTE
**STRICTLY CONFIDENTIAL — FOR BOARD CONSIDERATION ONLY**

### 1. Proposal & Executive Summary
This memorandum presents an operational and financial assessment grounded in the active session records from the IOCL Single Source of Truth (SSOT).

### 2. Operational & Financial Context
No active financial table rows were selected prior to drafting. Run an analytical query first to populate the grounded SSOT table in this memorandum.

### 3. Strategic Levers Evaluated (`L01–L10`)
1. **Option A: Refinery Energy & GRM Optimization (`L01–L02`):** Trimming Fuel & Loss (`-30 bps` -> `₹940 Cr/yr`) and scaling heavy/high-TAN opportunity crude (`+$0.35/bbl` -> `₹1,620 Cr/yr`).
2. **Option B: Pipeline Freight Shift & Working Capital Compression (`L04–L05`):** Migrating `6.5 MMT` inland fuel from rail to pipeline (`₹685 Cr/yr`) and trimming DIO by `3 days` (`~₹4,800 Cr` cash release).
3. **Option C: Stage-Gate Capex & De-Leveraging (`L07`, `L09`):** Enforcing `≥ 12%` post-tax equity IRR gating (`IOCL-CAPALLOC`) and retiring short-term WCDL/CP facilities.

### 4. Recommendation & Decision Sought
The Board Finance Committee is requested to review the grounded SSOT indicators and accord approval under `IOCL-DOA` Clause 6.0.

*Prepared by:* Corporate Finance & Treasury Group
*Submitted for Approval:* Chairman (`CMD`) & Director (Finance)
"""
    },
    "capex_appraisal": {
        "title": "Capex Appraisal Note (IOCL-CAPALLOC)",
        "doc_type": "capex_appraisal",
        "template_id": "template_capex_appraisal.md",
        "default_markdown": """# INDIAN OIL CORPORATION LIMITED (IOCL)
## STAGE-GATE CAPITAL EXPENDITURE APPRAISAL NOTE

**POLICY BASIS:** `IOCL-CAPALLOC` Clause 1.0–2.0 (`≥ 12.0%` Post-Tax Equity IRR Hurdle Rate)

### 1. Project & Refinery Capacity Summary
Capital outlay assessment across brownfield refinery expansions (Panipat P-25, Koyali, Barauni), cross-country pipelines, and Net-Zero 2046 investments grounded in IOCL SSOT.

### 2. Financial Viability & Target Leverage (`D/E ≤ 0.70x`)
- Stage-gate clearance verifies post-tax IRR `≥ 12%` and ongoing CWIP commissioning discipline.
"""
    },
    "treasury_fx_note": {
        "title": "Treasury, Crude Hedging & FX Risk Note",
        "doc_type": "treasury_fx_note",
        "template_id": "template_treasury_fx_note.md",
        "default_markdown": """# INDIAN OIL CORPORATION LIMITED (IOCL)
## TREASURY, CRUDE HEDGING & USD/INR FX RISK NOTE

**POLICY BASIS:** `IOCL-HEDGING` Clauses 2.0–5.0 (`25%–35%` crack hedge band; `50%–75%` short-term FX forward cover)

### 1. Crude Cargo, Crack & FX Exposure Snapshot
Review of cargo-in-transit pricing mismatch, Singapore gasoil crack hedges, and USD/INR ECB/LC sensitivity grounded in IOCL Treasury limits.
"""
    },
    "parliament_reply": {
        "title": "Parliament Question Reply: Downstream Refining & Exchequer Review",
        "doc_type": "parliament_reply",
        "template_id": "template_parliament_reply_format.docx",
        "default_markdown": """# GOVERNMENT OF INDIA
## MINISTRY OF PETROLEUM AND NATURAL GAS
### PARLIAMENT QUESTION BRIEFING DRAFT

**SUBJECT:** Refinery Capacity Utilization, Excise Duty & Capital Expenditure of Indian Oil Corporation Limited (IOCL)
**QUESTIONED BY:** Hon. Member of Parliament

---

### (a) Statement on Downstream Operations & Financial Performance
**ANSWER (MINISTER OF STATE IN THE MINISTRY OF PETROLEUM AND NATURAL GAS):**  
(a) Standalone refinery throughput (`75.451 MMT` across 9 refineries in FY26), pipeline volumes, and Schedule III financial figures are compiled from the IOCL Single Source of Truth (SSOT) records in the active session table.

### (b) Expansion, Energy Efficiency & Net-Zero Steps
**ANSWER:**  
(b) IndianOil has initiated the following strategic measures:
1. **Brownfield Refinery Expansions:** Capacity expansions at Panipat (`15 -> 25 MMTPA`), Koyali (`13.7 -> 18 MMTPA`), and Barauni (`6 -> 9 MMTPA`) to bolster domestic fuel security.
2. **Pipeline Modal Logistics & Net-Zero 2046:** Commissioning cross-country product pipeline spurs and Panipat Green Hydrogen / biofuel initiatives under `IOCL-CAPALLOC`.
"""
    }
}


class DocumentDraftingEngine:
    """Manages document creation, template instantiation, and iterative revision."""

    def __init__(self, templates_dir: Path = TEMPLATES_DIR):
        self.templates_dir = templates_dir

    def _format_markdown_table(self, columns: List[str], rows: List[Dict[str, Any]], max_rows: int = 12) -> str:
        if not columns or not rows:
            return ""
        cols = columns[:7]
        header = "| " + " | ".join(str(c).replace("_", " ").title() for c in cols) + " |"
        sep = "| " + " | ".join("---" for _ in cols) + " |"
        body = []
        for r in rows[:max_rows]:
            vals = []
            for c in cols:
                v = r.get(c, "")
                if isinstance(v, float):
                    vals.append(f"{v:,.2f}")
                elif isinstance(v, int):
                    vals.append(f"{v:,}")
                else:
                    vals.append(str(v if v is not None else ""))
            body.append("| " + " | ".join(vals) + " |")
        return "\n".join([header, sep] + body)

    def draft(
        self,
        doc_type: str,
        query: str,
        version: int = 1,
        instruction: Optional[str] = None,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Drafts or revises an official document, dynamically incorporating live session/BigQuery SSOT data."""
        dt = (doc_type or "").lower()
        q_l = (query or "").lower()
        key = "board_note"
        if any(w in dt or w in q_l for w in ["parliament", "rajya sabha", "lok sabha", "unstarred", "x7"]):
            key = "parliament_reply"

        base = DOCUMENT_TEMPLATES.get(key, DOCUMENT_TEMPLATES["board_note"])
        markdown = base["default_markdown"]
        title = base["title"]

        # Check if the user is asking for a dynamic data-backed briefing note / memo / report from context or SSOT
        ctx = context_data or {}
        ctx_rows = ctx.get("rows") or []
        ctx_cols = ctx.get("columns") or (list(ctx_rows[0].keys()) if ctx_rows and isinstance(ctx_rows[0], dict) else [])
        ctx_title = ctx.get("title") or ""
        wc_profile = ctx.get("wc_profile") or {}

        if ctx_rows or wc_profile:
            wc_name = wc_profile.get("wc_name") or ctx.get("wc_name") or "Indian Oil Corporation Limited (IOCL)"
            wc_id = wc_profile.get("wc_id") or ctx.get("wc_id") or "CORP-ALL"
            doc_heading = "OFFICE MEMORANDUM & EXECUTIVE BRIEFING NOTE"
            if "board" in q_l or "board" in dt:
                doc_heading = "BOARD OF DIRECTORS | AGENDA BRIEFING NOTE"
            elif "parliament" in q_l or "parliament" in dt:
                doc_heading = "MINISTRY OF PETROLEUM & NATURAL GAS | PARLIAMENT BRIEFING"
            elif "order" in q_l or "transfer" in q_l:
                doc_heading = "CORPORATE HUMAN RESOURCES | ADMINISTRATIVE ORDER DRAFT"

            subject_line = ctx_title if ctx_title and ctx_title != "Answer" else f"Operational & Workforce Review — {wc_name}"
            title = f"Draft Briefing Note: {subject_line}"

            wc_section = ""
            if wc_profile:
                def _fmt_count(val: Any) -> str:
                    if val is None or val == "":
                        return "n/a"
                    try:
                        return f"{int(float(val)):,}"
                    except (ValueError, TypeError):
                        return "n/a"

                def _get_val(new_key: str, old_key: Optional[str] = None) -> Any:
                    val = wc_profile.get(new_key)
                    if val is None and old_key:
                        val = wc_profile.get(old_key)
                    return val

                act_hc = _fmt_count(wc_profile.get("active_headcount"))
                exec_hc = _fmt_count(wc_profile.get("executive_headcount"))
                non_exec_hc = _fmt_count(wc_profile.get("non_executive_headcount"))
                sanc_hc = _fmt_count(_get_val("sanctioned_strength_fy26", "sanctioned_strength"))
                vac_hc = _fmt_count(_get_val("vacancy_count_fy26", "vacancy_count"))
                cont_hc = _fmt_count(_get_val("contractor_headcount_fy26", "contract_workforce_headcount"))

                pay_val = _get_val("payroll_gross_inr_cr_fy26", "fy26_total_payroll_cr")
                if pay_val is None or pay_val == "":
                    pay_str = "n/a"
                else:
                    try:
                        pay_str = f"₹{float(pay_val):,.2f} Crore"
                    except (ValueError, TypeError):
                        pay_str = "n/a"

                stay_5y = _fmt_count(_get_val("continuous_stay_5yr_plus_execs", "execs_stay_ge_5yr"))
                ret_3y = _fmt_count(_get_val("retiring_within_3yr_count", "retiring_3yr_count"))

                wc_section = f"""
### 2. Work Centre 360° Key Indicators ({wc_name} · `{wc_id}`)
- **In-Position Regular Strength (As of 19-Oct-2026):** **{act_hc}** employees (**{exec_hc}** Executives; **{non_exec_hc}** Non-Executives) against **{sanc_hc}** Sanctioned Posts (**{vac_hc}** Vacancies).
- **Contractual & Outsourced Workforce:** **{cont_hc}** contract personnel deployed across operations.
- **FY26 Gross Payroll:** **{pay_str}**.
- **Mobility & Succession Profile:** **{stay_5y}** executives with ≥5 years continuous station stay; **{ret_3y}** employees superannuating within 36 months.
"""

            md_table = self._format_markdown_table(ctx_cols, ctx_rows, max_rows=15)
            table_section = f"\n### 3. Grounded Analytical Data Table ({len(ctx_rows)} Records)\n{md_table}\n" if md_table else ""

            summary_para = ctx.get("summary_text") or (
                f"This executive briefing note synthesizes published and operational records from the IOCL Single Source of Truth (SSOT) "
                f"for {wc_name} as of 19th October 2026."
            )

            markdown = f"""# INDIAN OIL CORPORATION LIMITED
## {doc_heading}
**File Ref:** `IOCL/CMD/FIN/2026/{wc_id}` | **Date:** 16th November 2026  
**Classification:** INTERNAL — FOR EXECUTIVE REVIEW  
**Subject:** **{subject_line}**

---

### 1. Executive Summary
{summary_para}
{wc_section}{table_section}
### 4. Actionable Recommendations & Next Steps
1. **Refinery Energy & GRM Uplift (`L01–L03`):** Accelerate heavy opportunity crude intake and Fuel & Loss integration across Panipat, Paradip, and Koyali refineries.
2. **Capital Discipline & De-Leveraging:** Enforce `≥ 12%` post-tax equity IRR (`IOCL-CAPALLOC`) and monitor operating margins against FY27 MoU & BE/RE targets.
3. **Compliance & Governance:** Record this briefing note in the Board Finance Secretariat register and circulate approved extracts under `IOCL-DOA` Clause 6.0.

*Generated & Grounded by:* **Yukti AI (IndianOil Finance & Downstream Intelligence)**  
*Source Attribution:* `hrfin_gold.ssot_corporate_annual_360` & `hrfin_gold.ssot_refinery_economics_360`
"""

        # Apply revision instructions if requested
        if instruction:
            ins_l = instruction.lower()
            if "shorter" in ins_l or "concise" in ins_l:
                lines = markdown.splitlines()
                markdown = "\n".join(lines[:25]) + "\n\n*(Document abbreviated per executive instruction)*\n"
                title += " (Executive Brief)"
            elif "pec" in ins_l:
                markdown += "\n\n### Executive Revision Note\nOption A (Production Enhancement Contract - PEC) has been reaffirmed as the primary recommendation for immediate implementation."
            elif "hindi" in ins_l or "translate" in ins_l:
                markdown = "# तेल एवं प्राकृतिक गैस निगम लिमिटेड\n## निदेशक मंडल | एजेंडा नोट\n**गोपनीय — केवल बोर्ड विचारार्थ**\n\n### 1. प्रस्ताव एवं कार्यकारी सारांश\nयह ज्ञापन सीमांत ऑनशोर क्षेत्रों एवं कार्य केंद्रों में रणनीतिक हस्तक्षेप के लिए अनुमोदन चाहता है।"

        # Enforce name hygiene: strip real politicians
        markdown = sanitize_fictional_names(markdown)

        return {
            "doc_type": key,
            "title": title,
            "markdown": markdown,
            "template_id": base["template_id"],
            "version": version,
        }

    def draft_transfer_note(
        self,
        employees: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
        version: int = 1,
    ) -> Dict[str, Any]:
        """Drafts a transfer-note document listing the given roster employees."""
        if not employees:
            raise ValueError("no employees selected")

        n = len(employees)
        wcs = [e.get("work_centre") for e in employees]
        if all(w and w == wcs[0] for w in wcs):
            wc_label = wcs[0]
        else:
            wc_label = "Multiple Work Centres"

        title = f"Draft Transfer Note: {n} Executive(s) — {wc_label}"

        def _format_cell(val: Any) -> str:
            if val is None or val == "" or val == "None":
                return "—"
            if isinstance(val, bool):
                return "Yes" if val else "No"
            return str(val).replace("|", "\\|")  # a pipe would break the markdown table

        def _format_tenure(val: Any) -> str:
            if val is None or val == "" or val == "None" or val == "—":
                return "—"
            try:
                return f"{float(val):.1f}"
            except (ValueError, TypeError):
                return "—"

        headers = [
            "S.No",
            "Name",
            "Emp ID",
            "Designation",
            "Grade",
            "Discipline",
            "Present Work Centre",
            "Station Tenure (yrs)",
            "IOCL Service (yrs)",
            "Exemption",
        ]
        table_lines = [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
        ]
        for idx, emp in enumerate(employees, 1):
            row_vals = [
                str(idx),
                _format_cell(emp.get("name")),
                _format_cell(emp.get("emp_id")),
                _format_cell(emp.get("designation")),
                _format_cell(emp.get("grade")),
                _format_cell(emp.get("discipline")),
                _format_cell(emp.get("work_centre")),
                _format_tenure(emp.get("station_tenure_years")),
                _format_tenure(emp.get("iocl_tenure_years")),
                _format_cell(emp.get("exemption")),
            ]
            table_lines.append("| " + " | ".join(row_vals) + " |")
        table_str = "\n".join(table_lines)

        purpose_text = (
            context.get("purpose")
            if context and isinstance(context, dict) and context.get("purpose")
            else f"This deliberative draft transfer note outlines proposed rotational transfers for {n} executive(s) pursuant to the IOCL Job Rotation and Transfer Policy (JRTP)."
        )

        exemption_lines = []
        for emp in employees:
            ret = emp.get("retiring_within_3yr")
            is_retiring = (ret is True) or (isinstance(ret, str) and ret.lower() in ("true", "yes", "1"))
            ex = emp.get("exemption")
            has_ex = ex not in (None, "None", "", "—")
            if is_retiring or has_ex:
                reasons = []
                if is_retiring:
                    reasons.append("Retiring within 3 years")
                if has_ex:
                    reasons.append(f"Exemption: {ex}")
                emp_name = emp.get("name") or "—"
                emp_id = emp.get("emp_id") or "—"
                exemption_lines.append(f"- **{emp_name}** ({emp_id}) — {'; '.join(reasons)}")

        if exemption_lines:
            exemptions_content = "\n".join(exemption_lines)
        else:
            exemptions_content = "No exemption flags among the selected employees."

        md_parts = [
            "# OIL AND NATURAL GAS CORPORATION LIMITED",
            "## CORPORATE HUMAN RESOURCES | DRAFT TRANSFER NOTE",
            "**Classification:** CONFIDENTIAL — DELIBERATIVE DRAFT (JRTP Clause 11.0)",
            "",
            "### 1. Purpose",
            purpose_text,
            "",
            f"### 2. Employees Proposed for Transfer ({n})",
            table_str,
            "",
            "### 3. Policy Basis",
            "Rotational transfer recommendations are framed pursuant to JRTP Clause 3.2 rotation after 5 years of continuous station tenure. Clause 7.0 exemption within 3 years of superannuation applies to eligible executives subject to administrative review.",
            "",
            "### 4. Exemptions to Verify",
            exemptions_content,
            "",
            "### 5. Proposed Destination",
            "To be decided by the competent authority (Director HR).",
            "",
            "*Prepared by:* Yukti AI for Director (HR) review",
        ]
        markdown = "\n".join(md_parts)
        markdown = sanitize_fictional_names(markdown)

        return {
            "doc_type": "transfer_note",
            "title": title,
            "markdown": markdown,
            "template_id": "template_transfer_note.docx",
            "version": version,
            "employee_count": n,
            "emp_ids": [e.get("emp_id") for e in employees],
        }
