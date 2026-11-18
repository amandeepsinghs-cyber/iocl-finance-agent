"""QuerySpec planner (B2.2): Gemini structured output -> new QuerySpec or SpecPatch.

Input: the question, the previous QuerySpec (if any) and a catalog summary generated from
`semantic_model.yaml` + the entity dictionary. Output (JSON, schema-constrained) is turned
into a validated QuerySpec / SpecPatch here. Two deterministic guards run after the model:
the fiscal-year resolver (D-30) and the entity dictionary (codes must exist), so the LLM
never decides a period or an entity code on its own.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from functools import lru_cache
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

from app.brain.query_spec import Compare, Filter, Period, QuerySpec, Sort, SpecPatch, apply_patch
from app.brain.semantic_model import SemanticModel, get_semantic_model
from app.config import DEFAULT_TEXT_MODEL, GCP_PROJECT, VERTEX_TEXT_LOCATION
from app.semantic.entities import get_entities
from app.semantic.normalize import current_fy, fiscal_years_for_sql, last_complete_fy, resolve_fy

logger = logging.getLogger("yukti.brain.planner")

DIM_ALIASES = {"work_centre": "wc", "location": "wc", "station": "wc", "asset_wc": "asset", "fiscal_year": "fy",
               "year": "fy", "field_name": "field", "grade_id": "grade", "discipline_id": "discipline",
               "refinery_id": "refinery", "refinery_name": "refinery", "entity_code": "subsidiary",
               "product_code": "product", "pipeline_code": "pipeline"}


def normalize_asr_query(question: str) -> str:
    """Normalizes common speech-to-text phonetic mis-transcriptions for IOCL terms."""
    if not question:
        return ""
    q = question
    q = re.sub(r"\b(i\s*o\s*c\s*l|indian\s+oil|iocl\s+limited|nse\s+ioc)\b", "IOCL", q, flags=re.IGNORECASE)
    q = re.sub(r"\b([a-dA-D])\s*-\s*grade\b", lambda m: f"Grade {m.group(1).upper()}", q)
    q = re.sub(r"\bparadeep\b", "Paradip", q, flags=re.IGNORECASE)
    q = re.sub(r"\bkoyli\b", "Koyali", q, flags=re.IGNORECASE)
    return q

PLANNER_MODEL = os.getenv("YUKTI_PLANNER_MODEL", DEFAULT_TEXT_MODEL)
_OPS = ["=", "!=", ">", ">=", "<", "<=", "in", "not_in", "between", "like"]
_CHARTS = ["pie", "donut", "bar", "column", "hbar", "stacked_bar", "grouped_bar", "line", "area", "combo", "histogram",
           "box", "treemap", "heatmap", "waterfall", "bullet", "gauge", "funnel", "scatter", "kpi", "table", "map"]

PLAN_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "intent": {"type": "STRING", "enum": ["data", "replot", "policy", "what_if", "document", "chitchat", "other"]},
        "is_followup": {"type": "BOOLEAN"},
        "metric": {"type": "STRING"},
        "grain": {"type": "STRING", "enum": ["aggregate", "row"]},
        "set_dimensions": {"type": "BOOLEAN"},
        "dimensions": {"type": "ARRAY", "items": {"type": "STRING"}},
        "filters": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "field": {"type": "STRING"}, "op": {"type": "STRING", "enum": _OPS},
            "values": {"type": "ARRAY", "items": {"type": "STRING"}}}, "required": ["field", "op", "values"]}},
        "remove_filters": {"type": "ARRAY", "items": {"type": "STRING"}},
        "compare_field": {"type": "STRING"},
        "compare_values": {"type": "ARRAY", "items": {"type": "STRING"}},
        "fy": {"type": "STRING"},
        "fy_from": {"type": "STRING"},
        "fy_to": {"type": "STRING"},
        "sort_by": {"type": "STRING"},
        "sort_dir": {"type": "STRING", "enum": ["asc", "desc"]},
        "limit": {"type": "INTEGER"},
        "chart_kind": {"type": "STRING", "enum": _CHARTS},
    },
    "required": ["intent", "is_followup"],
}


@dataclass
class Plan:
    intent: str
    is_followup: bool = False
    spec: Optional[QuerySpec] = None            # the resulting full spec (new or patched)
    patch: Optional[SpecPatch] = None           # set for follow-ups / drill-downs
    chart_kind: Optional[str] = None
    notes: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0


@lru_cache(maxsize=1)
def catalog_summary() -> str:
    """Compact catalog for the planner prompt (generated, never hand-written)."""
    m: SemanticModel = get_semantic_model()
    ents = get_entities()
    from app.semantic.normalize import categorical_values

    # Auxiliary v3 schema subjects (employee_360 / employee_month / employee_fy) are served via
    # certified HR_E360_* queries and carry provenance tags ("Real"/"Synthetic") as labels that
    # shadow `workforce` in the LLM prompt. For `field_econ`, omit metrics that duplicate
    # canonical `field_pnl` / `lifting` metrics unless explicitly requested.
    skip_subjects = {"employee_360", "employee_month", "employee_fy"}
    shadow_field_econ_metrics = {
        "field_revenue_cr",
        "field_pbt_cr",
        "field_ebitda_cr",
        "field_ebitda_margin_pct",
        "lifting_cost_per_boe_usd",
    }

    lines: List[str] = ["SUBJECTS, METRICS AND FIELDS (use these names exactly):"]
    for s in m.subjects.values():
        if s.name in skip_subjects:
            continue
        metrics_items = [
            (mn, md) for mn, md in s.metrics.items()
            if not (s.name == "field_econ" and mn in shadow_field_econ_metrics)
        ]
        if not metrics_items:
            continue
        lines.append(f"- subject {s.name} [{s.domain}; period={s.period}{'; default ' + s.default_fy if s.default_fy else ''}]: {s.description}")
        lines.append("  metrics: " + "; ".join(f"{mn} = {md.label}" for mn, md in metrics_items))
        vals = categorical_values([s.table])
        fdesc = []
        for fn, fd in s.fields.items():
            if fn in ("delhi_tenure_years", "grade_level_order"):
                continue
            if fd.entity:
                fdesc.append(f"{fn} (code of {fd.entity})")
            elif fd.kind == "categorical":
                v = sorted(vals.get(fd.column.lower(), []))
                fdesc.append(f"{fn} in {v[:12]}" if v else fn)
            else:
                fdesc.append(f"{fn} ({fd.kind})")
        lines.append("  fields: " + "; ".join(fdesc))
        if s.row_columns:
            lines.append("  grain=row returns a list with: " + ", ".join(rc["as"] for rc in s.row_columns))
    for t in m.templates.values():
        lines.append(f"- analysis metric {t.name} [{t.domain}]: {t.description}")
    lines.append("- filter field `region` (any subject with wc/asset) values: " + ", ".join(sorted(ents._regions_cfg)))
    lines.append("\nWORK CENTRES (code: name, city): " + "; ".join(
        f"{c}: {a.get('short_name')} ({a.get('city')})" for c, a in ents.work_centres.items()))
    lines.append("DISCIPLINES: " + "; ".join(f"{c}: {a.get('name')}" for c, a in ents.disciplines.items()))
    if getattr(ents, "refineries", None):
        lines.append("REFINERIES & DIVISIONS: " + "; ".join(f"{c}: {a.get('name')}" for c, a in ents.refineries.items()))
    if getattr(ents, "subsidiaries", None):
        lines.append("SUBSIDIARIES & JVS: " + "; ".join(f"{c}: {a.get('name')}" for c, a in ents.subsidiaries.items()))
    if getattr(ents, "products", None):
        lines.append("PRODUCTS (MARKETING): " + "; ".join(f"{c}: {a.get('name')}" for c, a in ents.products.items()))
    if getattr(ents, "pipelines", None):
        lines.append("PIPELINES: " + "; ".join(f"{c}: {a.get('name')}" for c, a in ents.pipelines.items()))
    lines.append("GRADES (ordered): " + "; ".join(f"{c}: {a.get('name', a.get('designation', ''))[:40]}" for c, a in ents.grades.items()))
    return "\n".join(lines)


RULES = f"""You turn an IOCL (Indian Oil Corporation Limited) executive's question into a structured data plan. Output JSON only.
Intent: "data" for any question answerable from the subjects below (totals, rankings, trends,
comparisons); "replot" if the user only asks to show the SAME data as another chart/table; "policy" for
rules/DoA/hedging/accounting clauses/eligibility questions with no numbers; "what_if" for hypothetical simulations; "document" for
drafting Board notes/capex appraisals/letters/replies; "chitchat" for greetings; "other" if no subject fits (do not force a metric).
Questions about rules, norms, DoA thresholds, hedging mandates, procedures or "what is permitted" are "policy" even when they mention numbers.
Rules:
- metric MUST be one of the listed metric names. Pick the subject that holds the data.
- Follow-ups: if a previous plan is given and the question refines it (pronouns like "those", "this", "what about X", "only ...", "by ...", "compare with ...", "last year"), set is_followup=true and
  output ONLY what changes: new/replaced filters in `filters`, `remove_filters`, `set_dimensions`+`dimensions` for a new breakdown, `grain`, fy fields, metric if it changes.
  A brand-new topic is is_followup=false with a full plan.
- "by X" / "breakdown by X" / "X-wise" => set_dimensions=true, dimensions=[X]; back to aggregate if it was a list.
- "compare with B" / "versus B" => compare_field = the entity field (e.g. refinery), compare_values = [B]; keep the rest.
- Entities: use codes from the lists (refinery, subsidiary, product, pipeline, segment, category, wc).
- Fiscal years: current FY = {last_complete_fy()} ("last year" = {last_complete_fy()};
  "last N years" = N complete FYs ending {last_complete_fy()}). A resolved time hint may be supplied; follow it.
- Metric hints:
  company "profit and loss statement" / "P&L statement" / "income statement" / "complete P&L" => pnl_statement;
  company "balance sheet" / "assets and liabilities" / "statement of financial position" => balance_sheet;
  company "cash flow statement" / "statement of cash flows" / "cash flow bridge" => cash_flow_statement;
  company "financial ratios" / "key ratios" / "ratio analysis" / "credit ratios" / "solvency ratios" => financial_ratios;
  company "profit" / "PAT" / "munafa" => pat_cr; only "PBT"/"before tax" => pbt_corporate_cr; "EBITDA" => ebitda_cr;
  gross revenue => corporate_revenue_cr; net revenue (ex-excise) => net_revenue_cr; excise duty => excise_duty_cr;
  raw materials consumed => cost_of_materials_cr; DD&A / depreciation => dda_cr; tax expense => tax_expense_cr;
  total assets / non-current assets / current assets / CWIP / cash & bank / inventories / trade receivables / net worth / total debt / net debt / lease liabilities / total capex => matching corporate metric names;
  ROE / ROA / ROCE / debt-to-equity / current ratio / EPS / dividend per share / WACC => matching ratio/wacc metric;
  Inventory days (DIO) + Receivable days (DSO) + Net working capital cycle => working_capital;
  refinery GRM / margin / throughput / utilization / distillate yield / fuel & loss => refinery_economics subject (`refinery_grm_usd_bbl`, `refinery_throughput_mmt`, `refinery_utilization_pct`, `refinery_distillate_yield_pct`, `refinery_fuel_loss_pct`, `refinery_ebitda_cr`, `refinery_opex_usd_bbl`, dimension `refinery`);
  corporate reported/core GRM vs Singapore benchmark => `gross_refining_margin_usd_bbl`, `core_grm_usd_bbl`, `singapore_benchmark_grm_usd_bbl`;
  marketing volumes / petrol MS / diesel HSD / ATF / LPG Indane / Bitumen / SERVO => `marketing_volume_mmt` / `marketing_revenue_cr` / `marketing_market_share_pct` / `marketing_margin_inr_kl` (dimension `product`);
  pipelines throughput / utilization / tariff / EBITDA => `pipeline_throughput_mmt` / `pipeline_utilization_pct` / `pipeline_ebitda_cr` (dimension `pipeline`);
  Ind AS 108 statutory segments => `segment_revenue_cr` / `segment_ebit_cr` (dimension `segment`);
  MoU targets / Maharatna scorecard => `mou_scorecard` (subject `mou`);
  consolidated PAT / consolidated revenue / IOC.NS group => consolidated_pat_cr or consolidated_revenue_cr;
  subsidiaries (CPCL, LIOC / Lanka IOC, IOCME, IndOil Global, Petronet/HURL JVs) => subsidiary_pat_cr or subsidiary_revenue_cr (dimension subsidiary).
- Trends ("increased/decreased/changed over the last N years", "trend", "year by year") => add dimension fy.
- If the question needs a measure that is not listed, answer intent "other" instead of substituting a different metric.
- Never invent numbers; never write SQL.
"""


class Planner:
    def __init__(self, model: str = PLANNER_MODEL):
        self.model = model
        self._client: Optional[genai.Client] = None
        self.sm = get_semantic_model()
        self.ents = get_entities()

    @property
    def client(self) -> genai.Client:
        # The genai async transport binds to the event loop that first used it; re-create the client
        # when called from a different loop (tests, scripts) so a stale loop never breaks planning.
        try:
            loop_id = id(asyncio.get_running_loop())
        except RuntimeError:
            loop_id = None
        if self._client is None or getattr(self, "_client_loop", None) != loop_id:
            self._client = genai.Client(vertexai=True, project=GCP_PROJECT, location=VERTEX_TEXT_LOCATION)
            self._client_loop = loop_id
        return self._client

    def _prompt(self, question: str, prev: Optional[QuerySpec], history: List[str], fy_hint: Optional[Dict[str, Any]]) -> str:
        parts = [RULES, catalog_summary()]
        if prev is not None:
            parts.append("PREVIOUS PLAN (the answer currently on screen): " + json.dumps(prev.to_contract()))
        if history:
            parts.append("RECENT USER QUESTIONS (oldest first): " + " | ".join(history[-3:]))
        if fy_hint:
            parts.append(f"RESOLVED TIME HINT for this question: {json.dumps(fy_hint)}")
        parts.append(f"QUESTION: {question}")
        return "\n\n".join(parts)

    async def _call(self, prompt: str) -> Dict[str, Any]:
        cfg = types.GenerateContentConfig(
            temperature=0.0,
            response_mime_type="application/json",
            response_schema=PLAN_SCHEMA,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            max_output_tokens=1024,
        )
        resp = None
        for attempt in range(3):
            try:
                resp = await asyncio.wait_for(
                    self.client.aio.models.generate_content(model=self.model, contents=prompt, config=cfg),
                    timeout=12,
                )
                break
            except Exception as e:
                is_transient = isinstance(e, (asyncio.TimeoutError, TimeoutError)) or any(
                    tok in str(e) for tok in ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "Deadline")
                )
                if attempt < 2 and is_transient:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                raise
        text = (resp.text or "").strip() if resp else ""
        return json.loads(text) if text else {}

    # ------------------------------------------------------------ helpers
    def _subject_for(self, metric: str):
        subj, m, t = self.sm.resolve_metric(metric)
        return subj, m, t

    def _coerce_filter(self, f: Dict[str, Any], subject, notes: List[str]) -> Optional[Filter]:
        field = str(f.get("field", "")).strip()
        op = f.get("op") or "="
        vals = [str(v).strip() for v in (f.get("values") or []) if str(v).strip() != ""]
        if not field or not vals:
            return None
        fd = subject.fields.get(field) if subject is not None else None
        from app.brain.compiler import WC_ATTRIBUTE_FIELDS
        if field in WC_ATTRIBUTE_FIELDS and subject is not None and fd is None:
            return Filter(field=field, op="in" if op in ("=", "in") else op, value=vals) if op in ("=", "in", "!=", "not_in") else None
        if field != "region" and subject is not None and fd is None:
            fb = subject.dimension_fallbacks.get(field)
            if not fb:
                notes.append(f"dropped filter {field} (not in {subject.name})")
                return None
            field, fd = fb, subject.fields.get(fb)
        parsed: List[Any] = []
        for v in vals:
            if fd is not None and fd.kind == "number":
                m = re.search(r"-?\d+(?:\.\d+)?", v.replace(",", ""))
                if not m:
                    return None
                parsed.append(float(m.group(0)) if "." in m.group(0) else int(m.group(0)))
            elif fd is not None and fd.entity:
                code = self._entity(fd.entity, v)
                if not code and field == "field" and subject is not None and "asset" in subject.fields:
                    wc_code = self._entity("wc", v)
                    if wc_code and all(self._entity("wc", x) or self._entity("field", x) for x in vals):
                        field = "asset"
                        fd = subject.fields.get("asset")
                        parsed = [self._entity("wc", x) or self._entity("field", x) for x in vals]
                        parsed = [x for x in parsed if x]
                        break
                if not code:
                    notes.append(f"dropped unknown {fd.entity} '{v}'")
                    continue
                parsed.append(code)
            else:
                parsed.append(v)
        if not parsed:
            return None
        if op in ("in", "not_in"):
            return Filter(field=field, op=op, value=parsed)
        if op == "between":
            return Filter(field=field, op=op, value=parsed[:2]) if len(parsed) >= 2 else None
        if len(parsed) > 1 and op == "=":
            return Filter(field=field, op="in", value=parsed)
        return Filter(field=field, op=op, value=parsed[0])

    def _entity(self, etype: str, v: str) -> Optional[str]:
        tables = {
            "wc": self.ents.work_centres,
            "discipline": self.ents.disciplines,
            "field": self.ents.fields,
            "grade": self.ents.grades,
            "refinery": self.ents.refineries,
            "subsidiary": self.ents.subsidiaries,
            "product": self.ents.products,
            "pipeline": self.ents.pipelines,
        }
        table = tables.get(etype, {})
        if v in table:
            return v
        if v.upper() in table:
            return v.upper()
        resolvers = {
            "wc": self.ents.resolve_wc,
            "discipline": self.ents.resolve_discipline,
            "field": self.ents.resolve_field,
            "refinery": self.ents.resolve_refinery,
            "subsidiary": self.ents.resolve_subsidiary,
            "product": self.ents.resolve_product,
            "pipeline": self.ents.resolve_pipeline,
        }
        if etype in resolvers:
            return resolvers[etype](v)
        if etype == "grade":
            gs = self.ents.resolve_grades(v)
            return gs[0] if gs else None
        return None

    def _period(self, raw: Dict[str, Any]) -> Optional[Period]:
        fy, lo, hi = raw.get("fy"), raw.get("fy_from"), raw.get("fy_to")
        ok = lambda x: bool(x) and re.fullmatch(r"FY\d{2}", str(x).upper())
        if ok(fy):
            return Period(fy=str(fy).upper())
        if ok(lo) or ok(hi):
            return Period(**{"from": str(lo).upper() if ok(lo) else None, "to": str(hi).upper() if ok(hi) else None})
        return None

    def _fit_to_subject(self, spec: QuerySpec, notes: List[str]) -> QuerySpec:
        """After a metric change, map dimensions/filters to the new subject (e.g. field -> asset)."""
        subject, _, tdef = self._subject_for(spec.metric)
        if subject is None:
            return spec
        from app.brain.compiler import WC_ATTRIBUTE_FIELDS

        def fit(name: str) -> Optional[str]:
            if name in subject.fields or name == "region":
                return name
            if name in WC_ATTRIBUTE_FIELDS and ("wc" in subject.fields or "asset" in subject.fields):
                return name
            if name == "wc" and "asset" in subject.fields:
                return "asset"
            if name == "asset" and "wc" in subject.fields:
                return "wc"
            return subject.dimension_fallbacks.get(name)

        dims, filters = [], []
        for d in spec.dimensions:
            nd = fit(d)
            if nd and nd not in dims:
                dims.append(nd)
            if nd != d:
                notes.append(f"dimension {d} -> {nd}")
        for f in spec.filters:
            nf = fit(f.field)
            if nf:
                filters.append(Filter(field=nf, op=f.op, value=f.value))
            else:
                notes.append(f"filter {f.field} not applicable to {subject.name}")
        data = spec.model_dump(by_alias=True)
        data.update({"dimensions": dims, "filters": [x.model_dump() for x in filters], "domain": subject.domain})
        return QuerySpec.model_validate(data)

    # ------------------------------------------------------------ main
    async def plan(self, question: str, prev: Optional[QuerySpec] = None, history: Optional[List[str]] = None) -> Plan:
        t0 = time.perf_counter()
        question = normalize_asr_query(question)
        prev_subject = self._subject_for(prev.metric)[0] if prev else None
        avail = fiscal_years_for_sql(f"FROM {prev_subject.table}") if prev_subject else []
        fy_hint = resolve_fy(question, available=avail or None)
        ql_fast = question.lower()
        if prev is not None and re.match(
            r"^\s*(?:then\s+|so\s+|please\s+|ok\s+)?(?:show|give|display)\s+(?:it|that)(?:\s+to\s+me)?\s*[?!.]*$",
            ql_fast,
        ):
            return Plan(
                intent="data",
                is_followup=True,
                spec=prev,
                patch=SpecPatch(),
                chart_kind="table",
                notes=["repeat_prev_spec"],
                latency_ms=round((time.perf_counter() - t0) * 1000, 1),
            )
        # R2-M1: single-FY waterfall bridge requests ("Show FY23 P&L as a waterfall", "Show FY23 as a waterfall")
        # resolve deterministically to single-FY pnl_statement with chart_kind="waterfall" without waiting on LLM.
        if (
            re.search(r"\b(waterfall|bridge)\b|वॉटरफॉल|वाटरफॉल", ql_fast)
            and fy_hint
            and fy_hint.get("fy")
            and not fy_hint.get("from")
            and not self.ents.resolve_wcs(question)
            and not self.ents.resolve_field(question)
            and not re.search(r"\b(balance\s+sheet|cash\s*flow)\b", ql_fast)
        ):
            det_plan = self.to_plan(question, {}, prev, fy_hint)
            if det_plan.intent == "data" and det_plan.spec is not None:
                det_plan.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
                return det_plan
        try:
            raw = await asyncio.wait_for(self._call(self._prompt(question, prev, history or [], fy_hint)), timeout=30)
        except Exception as e:  # planner failure => try deterministic guards in to_plan first before legacy fallback
            logger.warning(f"planner call failed: {e}")
            det_plan = self.to_plan(question, {}, prev, fy_hint)
            if (det_plan.intent in ("data", "replot") and det_plan.spec is not None) or det_plan.intent in ("what_if", "document", "policy", "why"):
                det_plan.notes.append(f"recovered from llm error via deterministic guard: {str(e)[:80]}")
                det_plan.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
                return det_plan
            return Plan(intent="error", notes=[f"planner error: {str(e)[:120]}"],
                        latency_ms=round((time.perf_counter() - t0) * 1000, 1))
        plan = self.to_plan(question, raw, prev, fy_hint)
        plan.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        return plan

    def to_plan(self, question: str, raw: Dict[str, Any], prev: Optional[QuerySpec],
                fy_hint: Optional[Dict[str, Any]] = None) -> Plan:
        """Deterministic conversion + guards (unit-testable without the LLM)."""
        question = normalize_asr_query(question)
        if fy_hint is None:
            fy_hint = resolve_fy(question)
        intent = raw.get("intent") or "other"
        notes: List[str] = []
        chart = raw.get("chart_kind")
        ql_early = question.lower()
        # BEH-07.30 T3: "then show it to me" / "show it to me" repeats the last data spec in session
        if prev is not None and re.match(
            r"^\s*(?:then\s+|so\s+|please\s+|ok\s+)?(?:show|give|display)\s+(?:it|that)(?:\s+to\s+me)?\s*[?!.]*$",
            ql_early,
        ):
            return Plan(
                intent="data",
                is_followup=True,
                spec=prev,
                patch=SpecPatch(),
                chart_kind="table",
                notes=["repeat_prev_spec"],
                raw=raw,
            )
        wants_waterfall = bool(
            re.search(r"\b(waterfall|bridge)\b", ql_early)
            or (
                re.search(r"\b(revenue|income|sales|turnover)\b", ql_early)
                and re.search(r"\b(cost\w*|expense\w*|opex|levies|outflow\w*|deduction\w*|margin\w*|profit|pbt|pat)\b", ql_early)
                and re.search(r"\b(plot\w*|chart\w*|graph\w*|visual\w*|draw|show|display|view|compare)\b", ql_early)
                and not re.search(r"\b(table|tabular)\b", ql_early)
            )
            or (
                re.search(r"\b(plot\w*|chart\w*|graph\w*|visual\w*|draw)\b", ql_early)
                and re.search(r"\b(p\s*&\s*l|pnl|profit\s+and\s+loss|income\s+statement|revenue\s+and\s+cost\w*|revenue\s+vs\s+cost\w*)\b", ql_early)
                and not re.search(r"\b(table|tabular)\b", ql_early)
            )
        )
        if prev is not None:
            from app.brain.chart_rules import is_pure_replot_request
            is_replot_req, replot_k = is_pure_replot_request(question)
            if is_replot_req and replot_k:
                intent = "replot"
                chart = replot_k
        if intent == "replot" and prev is not None:
            raw_m = raw.get("metric")
            explicit_visual = bool(
                chart
                or wants_waterfall
                or re.search(
                    r"\b(chart|plot|graph|pie|donut|bar|hbar|line|area|table|tabular|waterfall|bridge|treemap|heatmap|scatter|gauge|bullet|funnel|histogram|box|visual\w*)\b",
                    ql_early,
                )
            )
            if (raw_m and raw_m != prev.metric) or not explicit_visual:
                intent = "data"
            elif prev.metric in ("pnl_statement", "balance_sheet", "cash_flow_statement", "financial_ratios", "wacc_pct", "wacc_components", "wacc_change_attribution"):
                ck = "waterfall" if wants_waterfall else (chart or "table")
                spec = prev.model_copy(update={"chart_kind": ck})
                return Plan(intent="data", is_followup=True, spec=spec, patch=SpecPatch(chart_kind=ck), chart_kind=ck, raw=raw)
            else:
                patch = SpecPatch(chart_kind=chart or "table")
                return Plan(intent="replot", is_followup=True, spec=prev, patch=patch, chart_kind=patch.chart_kind, raw=raw)
        no_sub_entity = (
            not self.ents.resolve_wcs(question)
            and not self.ents.resolve_field(question)
            and not re.search(r"\b(field|fields|basin|basins)\b", ql_early)
        )
        is_corp_bs_stmt = bool(
            re.search(r"\b(balance\s+sheet\w*|statement\s+of\s+financial\s+position|assets\s+and\s+liabilities|equity\s+and\s+liabilities)\b", ql_early)
            and no_sub_entity
        )
        is_corp_cf_stmt = bool(
            re.search(r"\b(cash\s*flow\s+statement\w*|statement\s+of\s+cash\s*flows|ind[- ]?as\s*7|cash\s*flow\s+bridge|cash\s*flow\s+waterfall)\b", ql_early)
            and no_sub_entity
        )
        is_corp_ratios_stmt = bool(
            re.search(r"\b(financial\s+ratios|key\s+ratios|ratio\s+analysis|ratios\s+scorecard|credit\s+ratios|solvency\s+ratios|return\s+ratios)\b", ql_early)
            and no_sub_entity
        )
        is_generic_fin_stmt = bool(
            re.search(r"\b(financial\s+statement\w*|annual\s+statement\w*|annual\s+report\s+statement\w*)\b", ql_early)
            and not re.search(r"\b(p\s*&\s*l|pnl|profit\s+and\s+loss|income\s+statement\w*|balance\s+sheet\w*|cash\s*flow\w*)\b", ql_early)
            and no_sub_entity
        )
        is_rev_cost_bridge = bool(
            re.search(r"\b(revenue|income|sales|turnover)\b", ql_early)
            and re.search(r"\b(cost\w*|expense\w*|opex|levies|outflow\w*)\b", ql_early)
            and no_sub_entity
            and not re.search(r"\b(asset|assets)\b", ql_early)
        )
        is_fy_waterfall_followup = bool(
            wants_waterfall
            and fy_hint
            and fy_hint.get("fy")
            and not fy_hint.get("from")
            and no_sub_entity
            and not is_corp_bs_stmt
            and not is_corp_cf_stmt
            and re.search(r"\b(show|plot|view|display|express|make|draw)\s+fy\s*\d{2}\b", ql_early)
        )
        is_corp_pnl_stmt = bool(
            (
                re.search(
                    r"\b(p\s*&\s*l|pnl|profit\s+and\s+loss|income\s+statement\w*|financial\s+statement\w*|"
                    r"annual\s+statement\w*|schedule\s+iii|published\s+annual\s+report)\b"
                    r"|(?:आय\s+विवरण|लाभ\s+और\s+हानि|प्रकाशित\s+वार्षिक\s+रिपोर्ट)",
                    ql_early,
                )
                or is_rev_cost_bridge
                or is_fy_waterfall_followup
            )
            and no_sub_entity
            and not is_corp_bs_stmt
            and not is_corp_cf_stmt
            and not is_corp_ratios_stmt
            and not re.search(r"\b(asset|assets)\b", ql_early)
        )
        explicit_chart_q = bool(
            re.search(
                r"\b(chart|plot|graph|waterfall|bridge|bar|hbar|column|line|area|combo|pie|donut|visuali[sz]e|diagram)\b"
                r"|चार्ट|ग्राफ|वॉटरफॉल|वाटरफॉल",
                ql_early,
            )
        )
        if is_corp_bs_stmt:
            intent = "data"
            raw = dict(raw, intent="data", metric="balance_sheet", is_followup=False, dimensions=[])
            if wants_waterfall:
                chart = "waterfall"
            elif explicit_chart_q and chart not in ("kpi", "table"):
                chart = chart
            else:
                chart = "table"
        elif is_corp_cf_stmt:
            intent = "data"
            raw = dict(raw, intent="data", metric="cash_flow_statement", is_followup=False, dimensions=[])
            if wants_waterfall:
                chart = "waterfall"
            elif explicit_chart_q and chart not in ("kpi", "table"):
                chart = chart
            else:
                chart = "table"
        elif is_corp_ratios_stmt:
            intent = "data"
            raw = dict(raw, intent="data", metric="financial_ratios", is_followup=False, dimensions=[])
            chart = chart if (explicit_chart_q and chart not in ("kpi", "table")) else "table"
        elif is_corp_pnl_stmt:
            intent = "data"
            raw = dict(raw, intent="data", metric="pnl_statement", is_followup=False, dimensions=[])
            if is_generic_fin_stmt:
                notes.append("ambiguous_financial_statement")
                chart = "waterfall" if re.search(r"\b(waterfall|bridge)\b", ql_early) else "table"
            elif wants_waterfall or is_rev_cost_bridge:
                chart = "waterfall"
            elif explicit_chart_q and chart not in ("kpi", "table"):
                chart = chart
            else:
                chart = "table"
        elif wants_waterfall and prev is not None and prev.metric in ("pnl_statement", "cash_flow_statement", "wacc_change_attribution", "wacc_components", "wacc_pct"):
            spec = prev.model_copy(update={"chart_kind": "waterfall"})
            return Plan(intent="data", is_followup=True, spec=spec, patch=SpecPatch(chart_kind="waterfall"), chart_kind="waterfall", raw=raw)

        is_wacc_q = bool(
            re.search(r"\b(wacc|weighted\s+average\s+cost\s+of\s+capital)\b", ql_early)
            and no_sub_entity
        )
        prev_is_wacc = bool(
            prev is not None
            and prev.metric in ("wacc_pct", "wacc_components", "wacc_build_up", "wacc_change_attribution")
        )
        if is_wacc_q or prev_is_wacc:
            is_why = bool(re.search(r"\b(why|what\s+drove|reason\w*|cause\w*|attribut\w*|how\s+come|rise|rose|fallen|drop\w*|high\w*|low\w*)\b", ql_early))
            is_components = bool(re.search(r"\b(build[- ]?up\s*/\s*driver\w*|component\w*|breakdown|build[- ]?up\s+and\s+components|stack\w*)\b", ql_early))
            is_single_build_up = bool(re.search(r"\b(parameter\w*|inputs?)\b", ql_early) or (re.search(r"\bbuild[- ]?up\b", ql_early) and not is_components and (fy_hint and fy_hint.get("fy"))))
            has_single_fy = bool(fy_hint and fy_hint.get("fy") and not fy_hint.get("from") and not is_why and not re.search(r"\b(past|last|\d+\s+years?|trend|history)\b", ql_early))
            if is_why:
                intent = "data"
                raw = dict(raw, intent="data", metric="wacc_change_attribution", is_followup=bool(prev_is_wacc and not is_wacc_q), dimensions=[])
                chart = "waterfall"
                if fy_hint and fy_hint.get("fy"):
                    raw["fy"] = fy_hint["fy"]
                elif not raw.get("fy"):
                    raw["fy"] = "FY23"
            elif is_components:
                intent = "data"
                raw = dict(raw, intent="data", metric="wacc_components", is_followup=bool(prev_is_wacc and not is_wacc_q), dimensions=[])
                chart = "stacked_bar"
                if not (raw.get("fy_from") or (fy_hint and fy_hint.get("from"))):
                    raw["fy_from"] = "FY22"
                    raw["fy_to"] = "FY26"
            elif is_single_build_up or has_single_fy:
                intent = "data"
                raw = dict(raw, intent="data", metric="wacc_build_up", is_followup=bool(prev_is_wacc and not is_wacc_q), dimensions=[])
                chart = "table"
                if fy_hint and fy_hint.get("fy"):
                    raw["fy"] = fy_hint["fy"]
                elif not raw.get("fy"):
                    raw["fy"] = "FY26"
            elif is_wacc_q:
                intent = "data"
                raw = dict(raw, intent="data", metric="wacc_pct", is_followup=False, dimensions=[])
                chart = "line"
                if re.search(r"\b(10\s+years?|ten\s+years?)\b", ql_early) or (fy_hint and fy_hint.get("n_years") == 10):
                    raw["fy_from"] = "FY17"
                    raw["fy_to"] = "FY26"
                elif not (raw.get("fy_from") or (fy_hint and fy_hint.get("from"))):
                    raw["fy_from"] = "FY22"
                    raw["fy_to"] = "FY26"

        # Hypothetical simulation guard ("If Brent falls to $60...", "What if crude drops...") — never capture forecast horizon extensions
        if re.search(
            r"\b(?:what[- ]if|if\s+(?:brent|crude|oil|gas|fx|rupee|usd|realisation)(?:\s+price)?\s+(?:falls?|drops?|rises?|goes|reaches|hits|were|is)\s+(?:to|below|above|by))\b",
            ql_early,
        ) and not re.search(r"\b(?:extend|project|extrapolate|stretch|continue)\b.{0,40}\b(?:202[7-9]|203\d|fy\s?2[7-9]|fy\s?3\d|forecast)\b", ql_early):
            return Plan(intent="what_if", raw=raw)

        # Document drafting guard ("Draft a transfer note...", "Draft a board note...")
        if re.search(
            r"^\s*(?:please\s+)?(?:draft|prepare|write|generate|create|compose)\b.*\b(?:note|memo|reply|letter|proposal|report|brief|order|document|minutes|email)\b",
            ql_early,
        ):
            return Plan(intent="document", raw=raw)

        # Policy rule guard ("What is the minimum tenure at a station as per the transfer policy?")
        if re.search(
            r"\b(?:as\s+per\s+(?:the\s+)?(?:transfer|leave|hr|jrtp)?\s*policy|minimum\s+tenure|maximum\s+tenure|what\s+is\s+the\s+rule)\b",
            ql_early,
        ) and not re.search(r"\b(how\s+many|kitne|count|list|names?)\b", ql_early):
            return Plan(intent="policy", is_followup=False, raw=dict(raw, intent="policy"))

        # Deterministic MoU scorecard & working-capital template overrides
        if (
            re.search(r"\b(tracking\s+against|mou\s+targets?|mou\s+scorecard|mou\s+performance|progress\s+on\s+mou)\b", ql_early)
            and not re.search(r"\b(framework|weightage|rule|policy|guideline|formula)\b", ql_early)
        ):
            intent = "data"
            raw = dict(raw, intent="data", metric="mou_scorecard", dimensions=[])
            if not raw.get("fy") and not (fy_hint and fy_hint.get("fy")):
                raw["fy"] = "FY26"
        elif (
            sum(1 for pat in (r"\binventory\s+days\b", r"\b(?:receivable|debtor)\s+days\b", r"\bworking\s+capital\b") if re.search(pat, ql_early)) >= 2
            or (raw.get("metric") == "financial_ratios" and re.search(r"\b(inventory\s+days|(?:receivable|debtor)\s+days|working\s+capital)\b", ql_early))
        ):
            intent = "data"
            raw = dict(raw, intent="data", metric="working_capital", dimensions=[])
        elif (
            re.search(r"\b(reconcil\w*|including)\b", ql_early)
            and re.search(r"\b(cpcl|lanka\s+ioc|lioc|subsidiar\w*)\b", ql_early)
            and re.search(r"\b(standalone|consolidated|pat|profit)\b", ql_early)
            and not re.search(r"\bonly\s+(?:cpcl|lanka|lioc)\b", ql_early)
        ):
            intent = "data"
            raw = dict(raw, intent="data", metric="subsidiary_pat_cr", dimensions=["subsidiary"], filters=[])

        # Deterministic Financial Causal & Action Guard ("Why did X happen?", "What action should the Finance Director take?")
        fin_kw = re.search(
            r"\b(wacc|weighted\s+average\s+cost\s+of\s+capital|"
            r"p\s*&\s*l|pnl|profit\s+and\s+loss|income\s+statement\w*|"
            r"pat|profit|pbt|revenue|ebitda|levies|royalty|oidb|saed|windfall|exploration|dry\s+well|survey\s+cost|"
            r"dd&a|dda|depreciation|impairment|115baa|deferred\s+tax|cwip|cpcl|lioc|lanka|iocme|indoil|petronet|hurl|subsidiar\w*|"
            r"borrowing\w*|debt|net\s+debt|lease\s+liabilit\w*|ind[- ]?as|excise|grm|refin\w*|distillate|throughput|pipeline\w*|marketing|petchem\w*|"
            r"cash\s*flow|ocf|fcf|free\s+cash|capex|mou|exchequer|dividend\w*|roce|roe|roa|eps|earnings\s+per\s+share|bvps|margin\w*|crude|"
            r"working\s+capital|inventory\s+days|receivable\s+days|debtor\s+days|"
            r"note\s+\d+|finance\s+director|director\s+finance)\b",
            ql_early,
        )
        prev_is_fin = bool(prev is not None and (prev.metric in ("pnl_statement", "balance_sheet", "cash_flow_statement", "financial_ratios") or prev_is_wacc))
        if not prev_is_fin and prev is not None:
            psubj, _, ptdef = self._subject_for(prev.metric)
            prev_is_fin = bool((psubj and psubj.domain == "finance") or (ptdef and ptdef.domain == "finance"))
        if intent not in ("what_if", "document", "policy", "replot") and (intent != "data" or not raw.get("metric")) and (fin_kw or (prev_is_fin and re.search(r"\b(why|what\s+happened|action|recommend\w*|interven\w*|improv\w*|explain|driver\w*|reason\w*|cause\w*|how)\b", ql_early))):
            inferred_m = raw.get("metric")
            if not inferred_m or not any(self._subject_for(inferred_m)):
                if is_wacc_q or (prev_is_wacc and re.search(r"\b(why|what|driver\w*|reason\w*|cause\w*|high\w*|low\w*)\b", ql_early)):
                    inferred_m = "wacc_change_attribution"
                    chart = "waterfall"
                elif re.search(r"\b(exchequer|contribution\s+to\s+exchequer)\b", ql_early):
                    inferred_m = "exchequer_contribution_cr"
                elif re.search(r"\bcapex\b", ql_early):
                    inferred_m = "capex_actual_cr"
                elif re.search(r"\bmou\b", ql_early):
                    inferred_m = "mou_scorecard"
                    if not raw.get("fy") and not (fy_hint and fy_hint.get("fy")):
                        raw = dict(raw, fy="FY26")
                elif re.search(r"\b(excise|statutory\s+levies|note\s+28)\b", ql_early):
                    inferred_m = "excise_duty_cr"
                elif re.search(r"\b(grm|gross\s+refining\s+margin)\b", ql_early):
                    inferred_m = "refinery_grm_usd_bbl"
                elif re.search(r"\b(dd&a|dda|depreciation|note\s+30)\b", ql_early):
                    inferred_m = "dda_cr"
                elif re.search(r"\b(cpcl|lioc|lanka|iocme|indoil|petronet|hurl|subsidiar\w*)\b", ql_early) and re.search(r"\b(investment\w*|stake|buyout|acqui\w*)\b", ql_early):
                    inferred_m = "investments_subsidiaries_jv_cr"
                elif re.search(r"\b(cpcl|lioc|lanka|iocme|indoil|petronet|hurl|subsidiar\w*)\b", ql_early):
                    inferred_m = "subsidiary_pat_cr"
                elif re.search(r"\b(borrowing\w*|debt|net\s+debt|note\s+16)\b", ql_early):
                    inferred_m = "total_debt_cr"
                elif re.search(r"\b(lease\s+liabilit\w*|ind[- ]?as\s*116|note\s+17)\b", ql_early):
                    inferred_m = "lease_liabilities_cr"
                elif re.search(r"\b(cwip|work[- ]in[- ]progress|note\s+6)\b", ql_early):
                    inferred_m = "cwip_cr"
                elif re.search(r"\b(free\s+cash\s+flow|fcf|operating\s+cash\s+flow|ocf|cash\s*flow)\b", ql_early):
                    inferred_m = "cash_flow_statement"
                elif re.search(r"\b(roce)\b", ql_early) and not re.search(r"\b(ratio\w*|scorecard)\b", ql_early):
                    inferred_m = "roce_pct"
                elif re.search(r"\b(working\s+capital|inventory\s+days|(?:receivable|debtor)\s+days)\b", ql_early):
                    inferred_m = "working_capital"
                elif re.search(r"\b(basic\s+eps|eps|earnings\s+per\s+share)\b", ql_early):
                    inferred_m = "eps_basic_inr"
                elif re.search(r"\b(roce|roe|roa|current\s+ratio|interest\s+coverage|debt[- ]to[- ]equity|ratio\w*)\b", ql_early):
                    inferred_m = "financial_ratios"
                elif re.search(r"\b(pipeline)\b", ql_early):
                    inferred_m = "pipeline_throughput_mmt"
                elif re.search(r"\b(marketing|petrol|diesel|atf|indane|servo)\b", ql_early):
                    inferred_m = "marketing_volume_mmt"
                elif re.search(r"\b(loss[- ]making\s+field\w*|lost\s+money|made\s+loss\w*|pec|field\s+profit\w*)\b", ql_early):
                    inferred_m = "pbt_cr"
                    if not raw.get("dimensions"):
                        raw = dict(raw, dimensions=["field"])
                    if re.search(r"\b(lost\s+money|loss[- ]making\s+field\w*)\b", ql_early) and not re.search(r"\b(most\s+profitable|profitable\s+and)\b", ql_early):
                        f_loss = list(raw.get("filters") or [])
                        if not any(isinstance(x, dict) and x.get("field") == "pbt_cr" for x in f_loss):
                            f_loss.append({"field": "pbt_cr", "op": "<", "values": ["0"]})
                        raw = dict(raw, filters=f_loss)
                elif re.search(r"\brevenue\b", ql_early) and re.search(r"\b(each\s+field|by\s+field|fields)\b", ql_early):
                    inferred_m = "revenue_cr"
                    if not raw.get("dimensions"):
                        raw = dict(raw, dimensions=["field", "fy"] if (fy_hint and fy_hint.get("from")) else ["field"])
                elif self.ents.resolve_field(question):
                    inferred_m = "pbt_cr"
                elif re.search(r"\b(pbt|before\s+tax)\b", ql_early) and no_sub_entity:
                    inferred_m = "pbt_corporate_cr"
                elif re.search(r"\b(profit|munafa|pat)\b", ql_early) and not re.search(r"\b(p\s*&\s*l|pnl|profit\s+and\s+loss|statement)\b", ql_early) and no_sub_entity:
                    inferred_m = "pat_cr"
                elif prev_is_wacc and prev is not None:
                    inferred_m = "wacc_change_attribution" if re.search(r"\b(why|what|driver\w*|reason\w*|cause\w*)\b", ql_early) else prev.metric
                    if inferred_m == "wacc_change_attribution":
                        chart = "waterfall"
                elif prev_is_fin and prev is not None:
                    inferred_m = prev.metric
                else:
                    inferred_m = "pnl_statement"
            intent = "data"
            is_fu_fin = bool(prev_is_fin and (inferred_m == (prev.metric if prev else None) or re.search(r"\b(same|these|those)\b", ql_early)))
            raw = dict(raw, intent="data", metric=inferred_m, is_followup=is_fu_fin)

        # SPEC-06 §4.3 / BUG-28: deterministic entry / starting pay scale guard -> pay_scale_min_inr
        is_entry_pay = bool(
            re.search(
                r"\b(starting\s+(?:basic\s+)?(?:pay|salary|scale)|entry[- ]?(?:level\s+)?(?:basic\s+)?(?:pay|salary|scale)|"
                r"minimum\s+(?:basic\s+)?(?:pay|scale)|get\s+on\s+joining|joining\s+(?:basic\s+)?(?:pay|salary|scale)|pay\s+scale\s+of\s+e[1-9])\b",
                ql_early,
            )
        )
        if is_entry_pay and (intent != "data" or not raw.get("metric")):
            g_match = re.search(r"\b(e[1-9])\b", ql_early, re.I)
            f_list = list(raw.get("filters") or [])
            if g_match and not any(f.get("field") == "grade" for f in f_list if isinstance(f, dict)):
                f_list.append({"field": "grade", "op": "=", "values": [g_match.group(1).upper()]})
            intent = "data"
            raw = dict(raw, intent="data", metric="pay_scale_min_inr", is_followup=False, dimensions=["grade"], filters=f_list)
        elif (intent != "data" or not raw.get("metric")) and re.search(
            r"(?:\b(?:average|avg\.?|mean|median)\s+(?:monthly\s+)?(?:basic\s+)?(?:salary|pay|ctc)\s+(?:of|for|by|across)\s+(?:e[1-9]\b|grade\w*)"
            r"|(?:e[1-9]\s*(?:अधिकारियों|कर्मचारियों)?\s*का\s*औसत\s*(?:मासिक\s*)?(?:मूल\s*)?(?:वेतन|सैलरी)))",
            ql_early,
        ):
            g_match = re.search(r"\b(e[1-9])\b", ql_early, re.I)
            f_list = list(raw.get("filters") or [])
            if g_match and not any(f.get("field") == "grade" for f in f_list if isinstance(f, dict)):
                f_list.append({"field": "grade", "op": "=", "values": [g_match.group(1).upper()]})
            intent = "data"
            raw = dict(raw, intent="data", metric="avg_gross_salary_lakh", is_followup=False, dimensions=["grade"], filters=f_list)

        # P2H.2 (M5): Policy & reporting process questions (e.g. POSH policy) resolve to intent="policy"
        from app.brain.rbac import is_policy_process_question
        if is_policy_process_question(question):
            return Plan(intent="policy", is_followup=False, raw=dict(raw, intent="policy"))

        # SPEC-06 §4.5 (M3): possessive first-person ("my", "mera/meri", "मेरा/मेरी") + immediate HR entity -> self_scope=True
        # Never match when "my" modifies a non-self noun ("in my opinion", "my team", "my colleagues", "my reporting officer")
        # or when plural/other-employee targets appear ("all ... officers", "each employee", "EMP-...").
        has_non_self_target = bool(
            re.search(
                r"\b(in\s+my\s+opinion|my\s+(?:team|colleague\w*|peer\w*|subordinate\w*|reporting\s+officer|boss|manager|department|division|section|unit)|"
                r"all\s+(?:e[1-9]\s+)?(?:hr\s+|finance\s+)?(?:officer\w*|executive\w*|employee\w*|staff)|"
                r"(?:each|every)\s+(?:officer|executive|employee)|emp-\d{4,6})\b",
                ql_early,
            )
        )
        is_self_hr = (not has_non_self_target) and bool(
            re.search(
                r"(?:"
                r"(?<![a-z])(?:my|mine|mera|meri|mere)(?:\s+(?:own|current|latest|monthly|annual|fy\d{2}|september|march|april|personal)){0,2}\s+"
                r"(?:salary|payslip|pay\s*slip|pay\s+components|pay\s+scale|ctc|basic\s*pay|da|hra|prp|gross\s*pay|net\s*pay|"
                r"leave|el|cl|hpl|balance|posting|postings|station|transfer|apar|rating|ratings|score|appraisal|"
                r"entitlement|entitlements|advance|advances|hba|car\s+advance|furniture|laptop|medical\s+claim\w*|reimbursement)(?![a-z])"
                r"|(?<![a-z])(?:how\s+long\s+have\s+i\s+been\s+posted|where\s+am\s+i\s+posted)(?![a-z])"
                r"|(?:मेरा|मेरी|मेरे|अपना|अपनी|अपने)\s+(?:\S+\s+){0,3}(?:वेतन|सैलरी|वेतन\s*पर्ची|पेस्लिप|payslip|salary|छुट्टी|पोस्टिंग|स्थानांतरण|एपार|apar|मूल्यांकन|पात्रता)"
                r")",
                question,
                re.I,
            )
        )
        if is_self_hr:
            raw = dict(raw, self_scope=True)
            if intent != "data" or not raw.get("metric"):
                intent = "data"
                raw = dict(raw, intent="data", metric="headcount", grain="row", is_followup=False, dimensions=[], filters=[])

        # SPEC-07 §4.1–4.3 (P2H.3): V19 Turn 1–3 deterministic guards (ordered levels, >5-yr cohort, named roster, all-cadres chip)
        is_all_cadres_chip = bool(
            prev is not None
            and re.search(r"\b(include\s+all\s+cadres|all\s+cadres|including\s+non[- ]?executives?)\b|सभी\s+कैडर", ql_early)
        )
        if is_all_cadres_chip and prev is not None:
            patch = SpecPatch(
                add_filters=[Filter(field="cadre", op="=", value="all")],
                dimensions=prev.dimensions or ["grade"],
                grain="aggregate",
                chart_kind="column",
            )
            spec = self._fit_to_subject(apply_patch(prev, patch), notes)
            return Plan(intent="data", is_followup=True, spec=spec, patch=patch, chart_kind="column", notes=notes, raw=raw)

        asks_level_breakdown = bool(
            re.search(
                r"\b(across\s+(?:different\s+)?levels?|by\s+levels?|level[- ]?wise|across\s+(?:different\s+)?grades?|by\s+grades?|grade[- ]?wise)\b",
                ql_early,
            )
            or re.search(r"(अलग-अलग\s+लेवल|लेवल\s+के\s+अनुसार|ग्रेड\s+के\s+अनुसार|अलग-अलग\s+ग्रेड|ग्रेड-वार|स्तर-वार)", question)
        )
        asks_histogram = bool(re.search(r"\bhistogram\b|हिस्टोग्राम", ql_early))
        asks_gt5_tenure = bool(
            re.search(
                r"(?:more\s+than\s+(?:5|five)\s+years?|(?:5|five)\s*\+\s*years?|(?:5|five)\s+years?\s+or\s+more|over\s+(?:5|five)\s+years?|"
                r"(?:paanch|panch|5)\s+saal\s+se\s+zyada|(?:पाँच|पांच|5)\s+(?:साल|वर्ष)\s+से\s+(?:ज़्यादा|ज्यादा|अधिक))",
                ql_early,
            )
            and not re.search(r"\b(minimum|maximum|policy\s+clause|what\s+is\s+the\s+rule)\b", ql_early)
        )
        asks_names = bool(
            re.search(
                r"\b(give\s+me\s+(?:the\s+)?names?|show\s+(?:the\s+)?names?|list\s+them|who\s+are\s+they|their\s+names?)\b",
                ql_early,
            )
            or re.search(r"(?:उनके|इनके|उन\s+कर्मचारियों\s+के)?\s*नाम.*(?:बताओ|दिखाओ|दे\s+दो)", question)
        )
        asks_names_followup = bool(prev is not None and asks_names and not asks_gt5_tenure)

        if asks_names_followup and prev is not None:
            intent = "data"
            sort_col = "delhi_tenure_years" if (
                re.search(r"\bdelhi\b|दिल्ली", ql_early)
                or any(f.field == "wc" and f.value == "WC-DEL" for f in (prev.filters or []))
            ) else (raw.get("sort_by") or "station_tenure_years")
            raw = dict(
                raw,
                intent="data",
                is_followup=True,
                metric=prev.metric or "headcount",
                grain="row",
                set_dimensions=True,
                dimensions=[],
                sort_by=sort_col,
                sort_dir="desc",
            )
        elif asks_gt5_tenure:
            is_fu_gt5 = bool(
                prev is not None
                and (
                    bool(raw.get("is_followup"))
                    or bool(re.search(r"\b(these|those|them|out\s+of\s+these|of\s+these|more\s+than\s+5\s+years\s+in\s+delhi)\b|इनमें|उनमें|ये|इन", ql_early))
                    or asks_names
                )
            )
            f_list = [
                (
                    {"field": "station_tenure_years", "op": ">=", "values": ["5"]}
                    if isinstance(x, dict)
                    and x.get("field") in ("station_tenure_years", "delhi_tenure_years", "continuous_stay_years")
                    and str((x.get("values") or [x.get("value")])[0] if (x.get("values") or x.get("value") is not None) else "") in ("5", "5.0")
                    else x
                )
                for x in (raw.get("filters") or [])
            ]
            if not any(isinstance(x, dict) and x.get("field") in ("station_tenure_years", "delhi_tenure_years", "total_tenure_years") for x in f_list):
                f_list.append({"field": "station_tenure_years", "op": ">=", "values": ["5"]})
            wants_all_cadres = bool(re.search(r"\b(all\s+cadres|including\s+non[- ]?executives?|non[- ]?executives?)\b|सभी\s+कैडर", ql_early))
            if not wants_all_cadres and not any(isinstance(x, dict) and x.get("field") == "cadre" for x in f_list):
                f_list.append({"field": "cadre", "op": "=", "values": ["executive"]})
            if asks_names:
                sort_col = "delhi_tenure_years" if re.search(r"\bdelhi\b|दिल्ली", ql_early) else (raw.get("sort_by") or "station_tenure_years")
                chart = "table"
                intent = "data"
                raw = dict(
                    raw,
                    intent="data",
                    is_followup=is_fu_gt5,
                    metric=raw.get("metric") or (prev.metric if is_fu_gt5 and prev else "headcount"),
                    grain="row",
                    set_dimensions=True,
                    dimensions=[],
                    filters=f_list,
                    sort_by=sort_col,
                    sort_dir="desc",
                )
            else:
                dims_gt5 = list(raw.get("dimensions") or [])
                if not dims_gt5:
                    dims_gt5 = ["grade"]
                if not chart or chart in ("bar", "histogram", "donut", "pie"):
                    chart = "column"
                intent = "data"
                raw = dict(
                    raw,
                    intent="data",
                    is_followup=is_fu_gt5,
                    metric=raw.get("metric") or (prev.metric if is_fu_gt5 and prev else "headcount"),
                    grain=raw.get("grain") or "aggregate",
                    set_dimensions=True,
                    dimensions=dims_gt5,
                    filters=f_list,
                )
        elif asks_level_breakdown and not is_self_hr:
            dims_lvl = list(raw.get("dimensions") or [])
            if "grade" not in dims_lvl and "grade_id" not in dims_lvl:
                dims_lvl = ["grade"] + dims_lvl
            f_list = list(raw.get("filters") or [])
            # T1 ("How many employees are posted in Delhi across different levels?"): keep all staff unless "executives"/"officers" was asked
            if not re.search(r"\b(executives?|officers?)\b|अधिकारी|एग्जीक्यूटिव", ql_early):
                f_list = [x for x in f_list if not (isinstance(x, dict) and x.get("field") == "cadre")]
            if asks_histogram:
                chart = "column"
                notes.append("level_histogram_requested")
            elif not chart or chart in ("histogram", "donut", "pie"):
                chart = "column"
            is_fu_lvl = bool(prev is not None and re.search(r"\b(these|those|them)\b|इनमें|उनमें", ql_early))
            intent = "data"
            raw = dict(
                raw,
                intent="data",
                is_followup=is_fu_lvl,
                metric=raw.get("metric") if raw.get("metric") in ("headcount", "avg_gross_salary_lakh", "pay_scale_min_inr", "separations", "voluntary_exits") else "headcount",
                grain="aggregate",
                set_dimensions=True,
                dimensions=dims_lvl,
                filters=f_list,
            )
        elif (intent != "data" or not raw.get("metric")) and not is_self_hr:
            if prev is not None and re.search(r"\b(break\s+it\s+down\s+by|breakdown\s+by|by\s+discipline)\b", ql_early):
                dim_fu = "discipline" if "discipline" in ql_early else ("grade" if "grade" in ql_early else "wc")
                intent = "data"
                raw = dict(raw, intent="data", is_followup=True, metric=prev.metric, grain="aggregate", set_dimensions=True, dimensions=[dim_fu])
            elif prev is not None and re.search(r"\bcompare\s+with\b", ql_early) and self.ents.resolve_wcs(question):
                intent = "data"
                raw = dict(raw, intent="data", is_followup=True, metric=prev.metric, grain="aggregate", compare_field="wc", compare_values=self.ents.resolve_wcs(question))
            elif prev is not None and re.search(r"\bonly\s+(e[1-9])\s+and\s+above\b", ql_early):
                m_ge = re.search(r"\bonly\s+(e[1-9])\s+and\s+above\b", ql_early)
                intent = "data"
                raw = dict(raw, intent="data", is_followup=True, metric=prev.metric, filters=[{"field": "grade", "op": ">=", "values": [m_ge.group(1).upper()]}])
            elif prev is not None and re.search(r"^\s*what\s+about\s+last\s+year\b", ql_early):
                prev_fy = prev.period.fy if (prev.period and prev.period.fy) else None
                target_fy = f"FY{int(prev_fy[2:]) - 1:02d}" if (prev_fy and prev_fy.startswith("FY") and prev_fy[2:].isdigit()) else "FY26"
                intent = "data"
                raw = dict(raw, intent="data", is_followup=True, metric=prev.metric, fy=target_fy)
            elif prev is not None and re.search(r"^\s*what\s+about\b", ql_early) and self.ents.resolve_wcs(question):
                intent = "data"
                raw = dict(raw, intent="data", is_followup=True, metric=prev.metric, filters=[{"field": "wc", "op": "=", "values": [self.ents.resolve_wcs(question)[0]]}])
            elif re.search(r"\bcapex\s+invested\b", ql_early):
                intent = "data"
                raw = dict(raw, intent="data", is_followup=False, metric="capex_actual_cr", grain="aggregate", dimensions=["asset"], fy_from="FY22", fy_to="FY26")
            elif re.search(r"\b(?:salary|apar)\b", ql_early) and re.search(r"\b(?:emp[- ]?)?(\d{5,6})\b", ql_early):
                m_emp = re.search(r"\b(?:emp[- ]?)?(\d{5,6})\b", ql_early)
                intent = "data"
                raw = dict(raw, intent="data", is_followup=False, metric="avg_gross_salary_lakh", grain="row", dimensions=[], filters=[{"field": "emp_id", "op": "=", "values": [f"EMP-{m_emp.group(1)}"]}])
            elif re.search(r"\b(?:average|avg)\s+(?:gross\s+)?salary\b", ql_early):
                intent = "data"
                raw = dict(raw, intent="data", is_followup=False, metric="avg_gross_salary_lakh", grain="aggregate", dimensions=["grade"])
            elif re.search(r"\bdetails?\s+of\s+employee\b", ql_early) and re.search(r"\b(?:emp[- ]?)?(\d{5,6})\b", ql_early):
                m_emp = re.search(r"\b(?:emp[- ]?)?(\d{5,6})\b", ql_early)
                intent = "data"
                raw = dict(raw, intent="data", is_followup=False, metric="headcount", grain="row", dimensions=[], filters=[{"field": "emp_id", "op": "=", "values": [f"EMP-{m_emp.group(1)}"]}])
            elif re.search(r"\bcompare\s+executives?\b", ql_early) and len(self.ents.resolve_wcs(question)) >= 2:
                dims_cmp = ["wc", "grade"] if "grade" in ql_early else ["wc"]
                intent = "data"
                raw = dict(raw, intent="data", is_followup=False, metric="headcount", grain="aggregate", dimensions=dims_cmp, filters=[{"field": "wc", "op": "in", "values": self.ents.resolve_wcs(question)}, {"field": "cadre", "op": "=", "values": ["executive"]}])
            elif re.search(r"\bvacanc(?:y|ies)\b", ql_early):
                dims_vac = ["wc", "discipline"] if "discipline" in ql_early else ["wc"]
                f_vac = [{"field": "region", "op": "=", "values": ["NE"]}] if re.search(r"\bnorth[- ]?east\b", ql_early) else []
                intent = "data"
                raw = dict(raw, intent="data", is_followup=False, metric="vacancies", grain="aggregate", dimensions=dims_vac, filters=f_vac)
            elif re.search(r"\bwomen\b", ql_early) and re.search(r"\b(work\s+centre|each\s+work\s+centre)\b", ql_early):
                intent = "data"
                raw = dict(raw, intent="data", is_followup=False, metric="headcount", grain="aggregate", dimensions=["wc"], filters=[{"field": "gender", "op": "=", "values": ["F"]}])
            elif re.search(r"\bretire\w*\b", ql_early) and re.search(r"\b3\s+years?\b", ql_early):
                f_ret = [{"field": "grade", "op": "=", "values": ["E7"]}] if re.search(r"\bgm\w*\b", ql_early) else []
                dims_ret = ["discipline"] if "discipline" in ql_early else []
                intent = "data"
                raw = dict(raw, intent="data", is_followup=False, metric="retiring_within_3yr", grain="aggregate", dimensions=dims_ret, filters=f_ret)
            elif re.search(r"\b(?:average|avg)\s+age\b", ql_early):
                intent = "data"
                raw = dict(raw, intent="data", is_followup=False, metric="avg_age", grain="aggregate", dimensions=[])
            elif re.search(r"\btraining\s+hours?\b", ql_early):
                f_trn = [{"field": "cadre", "op": "=", "values": ["executive"]}] if re.search(r"\bexecutive\w*\b", ql_early) else []
                dims_trn = ["discipline"] if "discipline" in ql_early else []
                intent = "data"
                raw = dict(raw, intent="data", is_followup=False, metric="training_hours_per_employee", grain="aggregate", dimensions=dims_trn, filters=f_trn)
            elif re.search(
                r"\b(how\s+many\s+(?:employees?|executives?|officers?|staff|people|personnel)|headcount|kitne\s+(?:employees?|executives?|officers?))\b|कितने\s+(?:कर्मचारी|अधिकारी)",
                ql_early,
            ):
                intent = "data"
                raw = dict(
                    raw,
                    intent="data",
                    is_followup=False,
                    metric="headcount",
                    grain="aggregate",
                    dimensions=list(raw.get("dimensions") or (["wc"] if len(self.ents.resolve_wcs(question)) >= 2 else ["grade"])),
                    filters=list(raw.get("filters") or []),
                )

        if intent != "data":
            return Plan(intent=intent, raw=raw)

        is_fu = bool(raw.get("is_followup")) and prev is not None
        metric = raw.get("metric") or (prev.metric if is_fu else None)
        # Guard against field_econ shadowing standard field_pnl / lifting metrics unless RAS/cost-object/field-econ is explicitly asked
        field_econ_to_canonical = {
            "field_revenue_cr": "revenue_cr",
            "field_pbt_cr": "pbt_cr",
            "field_ebitda_cr": "ebitda_cr",
            "field_ebitda_margin_pct": "ebitda_margin_pct",
            "lifting_cost_per_boe_usd": "lifting_cost_usd_per_boe",
        }
        if metric in field_econ_to_canonical and not re.search(
            r"\b(ras|cost\s+object|note\s+35|field\s+ebitda|field\s+economics|company\s+bridge)\b",
            ql_early,
        ):
            notes.append(f"canonicalized {metric} -> {field_econ_to_canonical[metric]}")
            metric = field_econ_to_canonical[metric]
        named_field = self.ents.resolve_field(question)
        if metric == "pnl_statement" and named_field:
            notes.append("canonicalized pnl_statement -> pbt_cr for named field")
            metric = "pbt_cr"
        subject, mdef, tdef = self._subject_for(metric) if metric else (None, None, None)
        if metric and not (mdef or tdef):
            if is_fu:
                metric = prev.metric
                subject, mdef, tdef = self._subject_for(metric)
            else:
                return Plan(intent="other", notes=[f"unknown metric {metric}"], raw=raw)
        if not metric:
            return Plan(intent="other", notes=["no metric"], raw=raw)

        filters = [f for f in (self._coerce_filter(x, subject, notes) for x in raw.get("filters") or []) if f]
        if named_field and subject is not None and "field" in subject.fields and not any(f.field == "field" for f in filters):
            filters.append(Filter(field="field", op="=", value=named_field))
            notes.append(f"entity guard added field={named_field}")
        from app.brain.compiler import WC_ATTRIBUTE_FIELDS
        if any(f.field in ("wc", "asset") for f in filters):
            # A named work centre makes state/sector/city/onshore_offshore filters redundant (and often wrong).
            dropped_attr = [
                f.field for f in filters
                if (
                    (f.field in WC_ATTRIBUTE_FIELDS and subject is not None and f.field not in subject.fields)
                    or (
                        f.field in ("onshore_offshore", "sector", "state")
                        and not re.search(r"\b(onshore|offshore|sector|state)\b", ql_early)
                    )
                )
            ]
            filters = [f for f in filters if f.field not in dropped_attr]
            if dropped_attr:
                notes.append(f"dropped redundant {dropped_attr}")
        dims = []
        for d in raw.get("dimensions") or []:
            d = DIM_ALIASES.get(d, d) if subject is not None and d not in subject.fields else d
            if subject is not None and d not in subject.fields:
                if d == "wc" and "asset" in subject.fields:
                    d = "asset"
                elif d == "asset" and "wc" in subject.fields:
                    d = "wc"
                elif d in subject.dimension_fallbacks:
                    d = subject.dimension_fallbacks[d]
                else:
                    notes.append(f"dropped dimension {d}")
                    continue
            if d not in dims:
                dims.append(d)
        period = self._period(raw)
        # Deterministic FY guard (D-30): an explicit time phrase in the question wins.
        if fy_hint:
            period = Period(fy=fy_hint["fy"]) if fy_hint.get("fy") else Period(**{"from": fy_hint.get("from"), "to": fy_hint.get("to")})
        grain = raw.get("grain")
        sort = Sort(by=raw["sort_by"], dir=raw.get("sort_dir") or "desc") if raw.get("sort_by") else None
        limit = raw.get("limit") if isinstance(raw.get("limit"), int) and raw.get("limit") > 0 else None
        if limit == 1 and not re.search(
            r"\b(top\s+1|bottom\s+1|first\s+1|last\s+1|limit\s+1|single|only\s+one|highest|lowest|largest|smallest|most|least)\b",
            ql_early,
        ):
            limit = None

        # Entity guard: a single work centre named in the question but missing from the plan.
        if wants_waterfall:
            chart = "waterfall"
        wc_field = None
        if subject is not None:
            wc_field = "wc" if "wc" in subject.fields else ("asset" if "asset" in subject.fields else None)
        named_wcs = self.ents.resolve_wcs(question)
        has_wc = any(f.field in ("wc", "asset", "region") for f in filters) or (
            bool(raw.get("compare_field")) and raw.get("compare_field") not in WC_ATTRIBUTE_FIELDS
        )
        if wc_field and len(named_wcs) == 1 and not has_wc and not self.ents.resolve_region(question):
            filters.append(Filter(field=wc_field, op="=", value=named_wcs[0]))
            notes.append(f"entity guard added {wc_field}={named_wcs[0]}")
            if not re.search(r"\b(onshore|offshore|sector|state)\b", ql_early):
                filters = [f for f in filters if f.field not in ("onshore_offshore", "sector", "state")]

        # Entity guard (multi): "Compare Delhi and Mumbai" named as states/cities instead of work centres.
        if (
            wc_field
            and len(named_wcs) >= 2
            and not any(f.field in ("wc", "asset") for f in filters)
            and (not raw.get("compare_field") or raw.get("compare_field") in WC_ATTRIBUTE_FIELDS)
            and not self.ents.resolve_region(question)
        ):
            filters = [
                f for f in filters
                if (f.field not in WC_ATTRIBUTE_FIELDS or f.field in subject.fields)
                and (f.field not in ("onshore_offshore", "sector", "state") or re.search(r"\b(onshore|offshore|sector|state)\b", ql_early))
            ]
            dims = [wc_field if d in ("state", "sector", "onshore_offshore") else d for d in dims]
            dims = list(dict.fromkeys(dims))
            raw = dict(raw, compare_field=wc_field, compare_values=named_wcs[:4])
            notes.append(f"entity guard: compare {wc_field} {named_wcs[:4]}")

        # Deterministic shape guards (golden-set findings):
        # (a) one work centre named, but the plan expanded it to every work centre in that city.
        if len(named_wcs) == 1:
            for i, f in enumerate(filters):
                if f.field in ("wc", "asset") and f.op == "in" and isinstance(f.value, list) \
                        and named_wcs[0] in f.value and len(f.value) > 4:
                    filters[i] = Filter(field=f.field, op="=", value=named_wcs[0])
        # (b) years at a place are station tenure unless total service is asked for.
        ql = question.lower()
        filters = [
            Filter(field="station_tenure_years", op=f.op, value=f.value)
            if f.field == "delhi_tenure_years" and subject is not None and "station_tenure_years" in subject.fields
            else f
            for f in filters
        ]
        g_code_match = re.search(r"\b(e[0-9])\b", ql, re.I)
        if g_code_match and subject is not None and "grade" in subject.fields:
            filters = [
                Filter(field="grade", op=f.op, value=g_code_match.group(1).upper())
                if f.field == "grade_level_order"
                else f
                for f in filters
            ]
        if named_wcs and not re.search(r"\b(service|with iocl|in iocl|with indianoil|career|joined|total tenure|total)\b", ql):
            filters = [Filter(field="station_tenure_years", op=f.op, value=f.value)
                       if f.field == "total_tenure_years" and subject is not None and "station_tenure_years" in subject.fields
                       else f for f in filters]
        # (c) "which refineries / subsidiaries / products / pipelines ..." asks for a ranking by that entity.
        if not dims and subject is not None and not is_fu and grain != "row":
            for word, d in (("refineries", "refinery"), ("subsidiaries", "subsidiary"), ("products", "product"),
                            ("pipelines", "pipeline"), ("segments", "segment"), ("fields", "field"),
                            ("assets", "asset"), ("work centres", "wc"), ("disciplines", "discipline"),
                            ("grades", "grade")):
                if re.search(rf"\b(which|what|top|bottom|list)\b.*\b{word}\b", ql):
                    d2 = d if d in subject.fields else ("wc" if d == "asset" and "wc" in subject.fields else
                                                        ("asset" if d == "wc" and "asset" in subject.fields else None))
                    if d2:
                        dims = [d2]
                        notes.append(f"shape guard: dimension {d2}")
                    break

        # (d) trend/history/profile wording over a period range, or a multi-year period with no other dimension => year-by-year breakdown.
        trend_q = re.search(
            r"\b(trend|increas\w*|decreas\w*|declin\w*|grew|grown|growth|changed|year[- ]by[- ]year|"
            r"over time|each year|every year|annual|yoy|year[- ]on[- ]year|by (?:fiscal |financial )?year|year[- ]?wise|"
            r"per year|yearly|fy[- ]?wise|history|historical|profile|trajectory|evolution|series)\b",
            ql,
        )
        multi_yr = bool(period is not None and period.from_ and period.to and period.from_ != period.to)
        non_fy_dims = [d for d in dims if d != "fy"]
        cumulative_only = bool(re.search(r"\b(cumulative|combined total|grand total)\b", ql) and not trend_q)
        if ((subject is not None and "fy" in subject.fields) or (tdef is not None and tdef.period == "fiscal_year")) and (period is not None and (period.from_ or period.to)):
            if trend_q or (multi_yr and not non_fy_dims and not cumulative_only):
                if "fy" not in dims:
                    if is_fu:
                        if raw.get("set_dimensions"):
                            dims = dims + ["fy"]
                        else:
                            raw = dict(raw, set_dimensions=True)
                            dims = [d for d in (prev.dimensions if prev else []) if d in subject.fields] + ["fy"]
                    else:
                        dims = dims + ["fy"]
                    notes.append("shape guard: trend/multi-year -> dimension fy")
                elif is_fu and not raw.get("set_dimensions"):
                    raw = dict(raw, set_dimensions=True)
                    base_dims = [d for d in (prev.dimensions if prev else []) if d in subject.fields and d != "fy"]
                    dims = base_dims + [d for d in dims if d not in base_dims]
        # (d2) a year-by-year breakdown only when the question asks for a trend/history/profile or is a multi-year series with no other grouping.
        keep_fy = bool(trend_q or (multi_yr and not non_fy_dims and not cumulative_only) or (is_fu and prev and "fy" in prev.dimensions))
        if "fy" in dims and not keep_fy:
            dims = [d for d in dims if d != "fy"]
            notes.append("shape guard: dropped fy dimension (no trend asked)")
        # (e) retention-rate style share metric is computed over everyone: drop a carried tenure filter.
        if metric == "long_stay_share_pct":
            raw = dict(raw, remove_filters=list(set((raw.get("remove_filters") or []) + ["station_tenure_years", "grade"])))
            filters = [f for f in filters if f.field not in ("station_tenure_years",)]
        # (f) "top N fields" / "most profitable fields" / "all fields" without "loss" drops a carried pbt_cr < 0 filter.
        if re.search(r"\b(top\s+\d+|most\s+profitable|all\s+fields)\b", ql) and not re.search(r"\bloss", ql):
            raw = dict(raw, remove_filters=list(set((raw.get("remove_filters") or []) + ["pbt_cr"])))
            filters = [f for f in filters if f.field != "pbt_cr"]

        compare = None
        if raw.get("compare_field") and raw.get("compare_values"):
            cf = raw["compare_field"]
            if subject is not None and cf not in subject.fields:
                cf = subject.dimension_fallbacks.get(cf, cf)
            fd = subject.fields.get(cf) if subject is not None else None
            if fd is not None:
                new_vals = []
                for v in raw["compare_values"]:
                    code = self._entity(fd.entity, str(v)) if fd.entity else str(v)
                    if code and code not in new_vals:
                        new_vals.append(code)
                if cf == "field" and len(new_vals) < len(raw["compare_values"]) and subject is not None and "asset" in subject.fields and len(named_wcs) >= 2:
                    cf = "asset"
                    fd = subject.fields.get("asset")
                    new_vals = list(dict.fromkeys(named_wcs[:4]))
                    dims = ["asset" if d == "field" else d for d in dims]
                base = []
                src = prev if is_fu else None
                cur = src.filter_on(cf) if src is not None else None
                if cur is not None:
                    base = cur.value if isinstance(cur.value, list) else [cur.value]
                for f in filters:
                    if f.field == cf:
                        base += f.value if isinstance(f.value, list) else [f.value]
                vals = list(dict.fromkeys(base + new_vals))
                filters = [f for f in filters if f.field != cf]
                if len(vals) >= 2:
                    compare = Compare(field=cf, values=vals[:4])
                elif vals:
                    filters.append(Filter(field=cf, op="=", value=vals[0]))

        if is_fu:
            rem_filters = [r for r in raw.get("remove_filters") or [] if isinstance(r, str)]
            if "station_tenure_years" in rem_filters and metric != "long_stay_share_pct" and not re.search(
                r"\b(all\s+tenures?|any\s+tenure|regardless|without\s+tenure|everyone|retention|share)\b",
                ql,
            ):
                rem_filters = [r for r in rem_filters if r != "station_tenure_years"]
            patch = SpecPatch(
                add_filters=filters,
                remove_filters=rem_filters,
                dimensions=dims if (raw.get("set_dimensions") or bool(dims)) else None,
                period=period if (period and (fy_hint or raw.get("fy") or raw.get("fy_from") or raw.get("fy_to"))) else None,
                grain=grain if grain and grain != prev.grain else None,
                metric=metric if metric != prev.metric else None,
                sort=sort, limit=limit, chart_kind=chart, compare=compare,
            )
            if patch.dimensions and prev.grain == "row" and patch.grain is None:
                patch.grain = "aggregate"  # "by discipline" after a names list returns to counts
            spec = self._fit_to_subject(apply_patch(prev, patch), notes)
            return Plan(intent="data", is_followup=True, spec=spec, patch=patch, chart_kind=chart, notes=notes, raw=raw)

        is_self_scope = bool(raw.get("self_scope"))
        if is_self_scope:
            filters = [f for f in filters if f.field != "wc"]
            grain = "row"
        spec = QuerySpec(domain=(subject.domain if subject else (tdef.domain if tdef else None)), metric=metric,
                         dimensions=[] if is_self_scope else dims, filters=filters, period=period,
                         grain=grain or "aggregate", sort=sort, limit=limit, self_scope=is_self_scope)
        if compare:
            spec = apply_patch(spec, SpecPatch(compare=compare))
        return Plan(intent="data", is_followup=False, spec=spec, chart_kind=chart, notes=notes, raw=raw)


_PLANNER: Optional[Planner] = None


def get_planner() -> Planner:
    global _PLANNER
    if _PLANNER is None:
        _PLANNER = Planner()
    return _PLANNER
