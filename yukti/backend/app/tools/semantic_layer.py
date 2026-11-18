"""Semantic Layer and SQL Safety Engine for Yukti AI.
Contains enterprise table schemas, metric definitions, join paths,
and enforces query-craft rules and SQL safety checks.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from google.cloud import bigquery

from app.semantic.normalize import normalize_categorical_filters
from app.config import (
    ALLOWED_DATASETS,
    BQ_LOCATION,
    GCP_PROJECT,
    JOB_LABELS,
    MAX_BYTES_BILLED,
)

logger = logging.getLogger("yukti.semantic_layer")

FORBIDDEN_SQL_PATTERNS = [
    r"\bINSERT\b",
    r"\bUPDATE\b",
    r"\bDELETE\b",
    r"\bDROP\b",
    r"\bALTER\b",
    r"\bCREATE\b",
    r"\bTRUNCATE\b",
    r"\bRENAME\b",
    r"\bGRANT\b",
    r"\bREVOKE\b",
    r"\bMERGE\b",
    r"\bEXECUTE\b",
    r"\bCALL\b",
    r"\bEXPORT\b",
    r"\bLOAD\b",
    r"\bEXTERNAL_QUERY\b",
    r"\bINFORMATION_SCHEMA\b",
    r"\bSESSION_USER\b",
    r"\b__TABLES__\b",
]

SEMANTIC_LAYER_PROMPT = f"""
BIGQUERY ENTERPRISE SCHEMAS & EXACT COLUMN CATALOG (Project: {GCP_PROJECT}):

0. AUTHORITATIVE SINGLE SOURCE OF TRUTH (SSOT) DOWNSTREAM 360° & FINANCIAL TABLES:
   • `hrfin_gold.ssot_corporate_annual_360` (1 ROW PER FISCAL YEAR — FY17–FY26):
     - Exact Columns: fiscal_year, gross_revenue_inr_cr, petroleum_products_revenue_inr_cr, petchem_and_other_op_rev_inr_cr, refining_marketing_revenue_inr_cr, petchem_revenue_inr_cr, pipelines_other_op_rev_inr_cr, other_income_inr_cr, total_income_inr_cr, statutory_levies_total_inr_cr, excise_duty_inr_cr, net_revenue_inr_cr, cost_of_materials_consumed_inr_cr, purchases_stock_in_trade_inr_cr, inventory_change_inr_cr, employee_benefit_net_pnl_inr_cr, other_expenses_inr_cr, operating_expenses_total_inr_cr, ebitda_inr_cr, ebit_inr_cr, dda_inr_cr, finance_costs_inr_cr, total_expenses_inr_cr, pbt_pre_exc_inr_cr, exceptional_items_inr_cr, pbt_inr_cr, current_tax_inr_cr, deferred_tax_inr_cr, tax_expense_total_inr_cr, pat_inr_cr, consolidated_revenue_inr_cr, consolidated_ebitda_inr_cr, consolidated_pbt_inr_cr, consolidated_pat_inr_cr, consolidated_net_worth_inr_cr, consolidated_total_debt_inr_cr, refinery_petchem_ppe_inr_cr, cwip_inr_cr, investments_subsidiaries_jv_inr_cr, other_non_current_assets_inr_cr, non_current_assets_inr_cr, inventories_inr_cr, current_investments_inr_cr, receivables_outstanding_inr_cr, cash_and_bank_inr_cr, other_current_assets_inr_cr, current_assets_inr_cr, total_assets_inr_cr, equity_share_capital_inr_cr, other_equity_reserves_inr_cr, net_worth_inr_cr, long_term_debt_inr_cr, lease_liabilities_non_current_inr_cr, deferred_tax_liability_net_inr_cr, other_non_current_liabilities_inr_cr, non_current_liabilities_inr_cr, short_term_debt_inr_cr, trade_payables_inr_cr, other_current_liabilities_inr_cr, current_liabilities_inr_cr, total_liabilities_inr_cr, total_equity_and_liabilities_inr_cr, total_debt_inr_cr, net_debt_inr_cr, net_working_capital_inr_cr, capital_employed_inr_cr, total_capex_spent_inr_cr, operating_cash_flow_inr_cr, investing_cash_flow_inr_cr, financing_cash_flow_inr_cr, free_cash_flow_inr_cr, ebitda_margin_pct, pat_margin_pct, roce_pct, standalone_roce_pct, roe_pct, roa_pct, debt_to_equity_ratio, net_debt_to_ebitda_ratio, interest_coverage_ratio, current_ratio, receivable_days, inventory_days, eps_basic_inr, book_value_per_share_inr, dividend_per_share_inr, total_dividend_payout_inr_cr, wacc_pct, brent_avg_usd_bbl, fx_inr_per_usd, singapore_benchmark_grm_usd_bbl, gross_refining_margin_usd_bbl, core_grm_usd_bbl, grm_premium_over_singapore_usd_bbl, refining_capacity_mmtpa, refining_throughput_mmt, refining_capacity_utilization_pct, distillate_yield_pct, fuel_and_loss_pct, pipeline_throughput_mmt, marketing_sales_mmt, exchequer_contribution_inr_cr, csr_disbursed_inr_cr.
     - Example: `SELECT fiscal_year, gross_revenue_inr_cr, excise_duty_inr_cr, net_revenue_inr_cr, ebitda_inr_cr, pat_inr_cr, consolidated_pat_inr_cr FROM hrfin_gold.ssot_corporate_annual_360 ORDER BY fiscal_year`

   • `hrfin_gold.ssot_refinery_economics_360` & `hrfin_gold.v_refinery_pnl_v3` (9 IOCL Standalone Refineries + 3 Division Recon Rows × 10 FYs):
     - Exact Columns: pnl_id, fiscal_year, unit_type, is_refinery, refinery_id, refinery_name, state, region, installed_capacity_mmtpa, throughput_mmt, capacity_utilization_pct, grm_usd_bbl, opex_usd_bbl, distillate_yield_pct, fuel_and_loss_pct, gross_revenue_inr_cr, excise_duty_inr_cr, net_revenue_inr_cr, other_income_inr_cr, employee_cost_inr_cr, crude_and_opex_inr_cr, ebitda_inr_cr, dda_inr_cr, finance_costs_inr_cr, pbt_pre_exc_inr_cr, exceptional_items_inr_cr, pbt_inr_cr.
     - MANDATORY: Filter `is_refinery = TRUE` for refinery rankings/comparisons (`REF-PNP` Panipat, `REF-PRD` Paradip, `REF-KYL` Koyali, `REF-MTR` Mathura, `REF-HLD` Haldia, `REF-BRN` Barauni, `REF-BNG` Bongaigaon, `REF-GHY` Guwahati, `REF-DGB` Digboi = `70.25 MMTPA` combined).

   • `hrfin_gold.fact_marketing_sales` (7 Product Categories × 10 FYs):
     - Exact Columns: marketing_record_id, fiscal_year, product_code, product_category, product_group, sales_volume_mmt, prior_fy_volume_mmt, yoy_volume_growth_pct, market_share_india_pct, revenue_inr_cr, gross_marketing_margin_inr_kl, unit, notes.

   • `hrfin_gold.fact_pipeline_ops` (3 Cross-Country Pipeline Networks × 10 FYs):
     - Exact Columns: pipeline_record_id, fiscal_year, pipeline_code, pipeline_type, pipeline_length_km, installed_capacity_mmtpa, throughput_mmt, capacity_utilization_pct, tariff_revenue_inr_cr, ebitda_inr_cr, unit_operating_cost_inr_mt, notes.

   • `hrfin_gold.fact_segment` (Ind AS 108 Statutory Segments):
     - Exact Columns: fiscal_year, scope, segment_code, line_code, metric, value_inr_mn, value_inr_cr, source_doc, verified, notes.

   • `hrfin_gold.fact_mou_scorecard` (DPE / MoPNG Maharatna MoU Targets FY25–FY26):
     - Exact Columns: fiscal_year, parameter_id, parameter_name, category, unit_of_measure, weightage, very_good_target, excellent_target, actual_achievement, achieved_rating, projected_composite_score.

   • `hrfin_gold.fact_wacc_annual` & `hrfin_gold.fact_wacc_input` (IOC.NS WACC FY17–FY26):
     - `fact_wacc_annual` Exact Columns: fiscal_year, rf_used_pct, erp_total_pct, beta_2y_weekly_adj, beta_industry_relevered, kd_used_pct, tax_rate_pct, weight_equity, weight_debt, ke_pct, wacc_pct, verified, notes.

   • `hrfin_silver.subsidiary_financials` (Group Entities Reconciling Standalone to Consolidated `IOC.NS`):
     - Exact Columns: subsidiary_record_id, entity_code, entity_name, fiscal_year, iocl_equity_holding_pct, revenue_inr_cr, ebitda_inr_cr, pat_inr_cr, iocl_share_pat_inr_cr, net_margin_pct, roce_pct, dividend_declared_inr_cr, dividend_received_by_iocl_inr_cr, refining_throughput_mmt, gross_refining_margin_usd_bbl.

   • `hrfin_gold.v_fin_statement_as_reported` & `hrfin_gold.v_fin_trend_latest` (Schedule III Line-Item SSOT):
     - Exact Columns: fiscal_year, scope, statement, line_code, display_name, display_order, level, line_kind, section, ar_note_ref_typical, value_inr_cr, value, unit, is_restated, footnote_marker, source_doc, source_page_label, source_system, verified.

3. THE 5 CRITICAL QUERY-CRAFT RULES:
   Rule 1: Always use `LOWER()` on string filters if unsure of case (e.g. `LOWER(scope) = 'standalone'`).
   Rule 2: NEVER SUM OR AVG PRE-COMPUTED PER-BARREL METRICS OR PERCENTAGES across refineries: always compute throughput-weighted averages (`SUM(grm_usd_bbl * throughput_mmt) / NULLIF(SUM(throughput_mmt), 0)`).
   Rule 3: Always distinguish Gross Revenue (incl. Excise) vs Net Revenue (ex-Excise) per Ind AS 115 Note 28, and filter `is_refinery = TRUE` on `ssot_refinery_economics_360` when ranking refineries so Marketing/Pipeline/Corporate division lines are not double-counted.
   Rule 4: Combine policy retrieval (`search_policy` / `doc_chunks_ar`) with quantitative SSOT tables (`query_data`) whenever answering governance + financial impact questions.
   Rule 5: Always include clear `ORDER BY` and sensible `LIMIT` on rankings.
"""


class SemanticLayer:
    """Manages enterprise metrics, glossary terms, and query safety."""

    def __init__(self, project_id: str = GCP_PROJECT, location: str = BQ_LOCATION):
        self.project_id = project_id
        self.location = location
        self._bq_client: Optional[bigquery.Client] = None

    @property
    def client(self) -> bigquery.Client:
        if self._bq_client is None:
            self._bq_client = bigquery.Client(
                project=self.project_id,
                location=self.location,
                default_query_job_config=bigquery.QueryJobConfig(labels=JOB_LABELS),
            )
        return self._bq_client

    def apply_query_craft_rules(self, sql: str) -> str:
        """Applies query-craft rules (project qualification, categorical normalization, and row limits)."""
        refined_sql = sql

        refined_sql = normalize_categorical_filters(refined_sql)

        from app.config import rewrite_dataset_sql
        refined_sql = rewrite_dataset_sql(refined_sql)
        pattern = r"(?<![a-zA-Z0-9_\-\.`])(hrfin_(?:gold|silver|docs|ref)(?:_v3)?)\.([a-zA-Z0-9_]+)"
        refined_sql = re.sub(pattern, f"`{self.project_id}`.\\1.\\2", refined_sql)

        refined_sql = re.sub(
            r"\bscope\s*=\s*'([Ss]tandalone|[Cc]onsolidated)'",
            lambda m: f"LOWER(scope) = '{m.group(1).lower()}'",
            refined_sql,
            flags=re.IGNORECASE,
        )

        if "LIMIT" not in refined_sql.upper() and not re.search(r"^\s*SELECT\s+COUNT\(", refined_sql, flags=re.IGNORECASE):
            # Aggregated (GROUP BY) results feed totals/insights, so a 100-row cap silently
            # produced wrong totals. Keep a generous cap for aggregates; 100 for raw row listings.
            is_aggregate = bool(re.search(r"\bGROUP\s+BY\b", refined_sql, flags=re.IGNORECASE))
            refined_sql = refined_sql.rstrip().rstrip(";") + (" LIMIT 5000;" if is_aggregate else " LIMIT 100;")
        return refined_sql

    def validate_sql_safety(self, sql: str) -> Tuple[bool, Optional[str]]:
        """Enforces SELECT-only queries, project + dataset allow-listing, and absence of forbidden statements (H1.2)."""
        if not sql or not sql.strip():
            return False, "Empty SQL query."

        # 1. Strip block/line comments and mask string literals so comments/strings cannot hide or fake tokens
        no_comments = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
        no_comments = re.sub(r"--[^\r\n]*", " ", no_comments)
        masked = re.sub(r"'(?:\\.|''|[^'])*'", "''", no_comments)
        masked = re.sub(r'"(?:\\.|""|[^"])*"', '""', masked)

        sql_stripped = masked.strip().rstrip(";").strip()
        if ";" in sql_stripped:
            return False, "Multiple SQL statements are not permitted."

        sql_upper = sql_stripped.upper()
        if not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
            return False, "Query must start with SELECT or WITH (read-only queries only)."

        for pattern in FORBIDDEN_SQL_PATTERNS:
            if re.search(pattern, sql_upper):
                return False, f"Forbidden SQL operation detected matching: {pattern}"

        # 2. Collect CTE aliases declared in WITH clauses so `FROM <cte>` is allowed
        cte_names = {
            m.group(1).lower()
            for m in re.finditer(r"(?:\bWITH\b|,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\s*\(", sql_stripped, flags=re.IGNORECASE)
        }

        # 3. Normalize backticked identifier chains (e.g. `other-proj`.ds.t or `other-proj.ds.t` or `p`.`d`.`t`)
        norm_ids = re.sub(r"`([^`]+)`", lambda m: m.group(1).replace(" ", ""), sql_stripped)
        norm_ids = re.sub(r"\s*\.\s*", ".", norm_ids)

        # 4. Every 3-part reference anywhere in the query must belong to (self.project_id, ALLOWED_DATASETS)
        three_part = re.findall(r"(?<![a-zA-Z0-9_\-.])([a-zA-Z0-9_\-]+)\.([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)", norm_ids)
        for proj, dataset, _table in three_part:
            if proj != self.project_id:
                return False, f"Project '{proj}' is not in the allowed project '{self.project_id}'."
            if dataset not in ALLOWED_DATASETS:
                return False, f"Dataset '{dataset}' is not in the allowed list: {ALLOWED_DATASETS}"

        # 5. Every FROM / JOIN target (excluding subqueries `(`, UNNEST, and CTEs) must be in ALLOWED_DATASETS
        #    Note: avoid `\s+` in lookbehind (Python `re` requires fixed-width lookbehind).
        for m in re.finditer(r"\b(?:FROM|JOIN)\s+([a-zA-Z0-9_\-.]+)", norm_ids, flags=re.IGNORECASE):
            ref = m.group(1).strip(".")
            # Skip date/extract tokens like `EXTRACT(YEAR FROM col)` by checking preceding token isn't EXTRACT(...)
            prefix = norm_ids[max(0, m.start() - 40):m.start()].upper()
            if "EXTRACT(" in prefix or "SUBSTRING(" in prefix or "TRIM(" in prefix:
                continue
            parts = ref.split(".")
            if len(parts) == 3:
                proj, dataset, _table = parts
                if proj != self.project_id:
                    return False, f"Project '{proj}' is not in the allowed project '{self.project_id}'."
                if dataset not in ALLOWED_DATASETS:
                    return False, f"Dataset '{dataset}' is not in the allowed list: {ALLOWED_DATASETS}"
            elif len(parts) == 2:
                dataset, _table = parts
                if dataset not in ALLOWED_DATASETS:
                    return False, f"Dataset '{dataset}' is not in the allowed list: {ALLOWED_DATASETS}"
            elif len(parts) == 1:
                ident = parts[0].lower()
                if ident not in cte_names and ident not in ("unnest",):
                    return False, f"Unqualified table '{parts[0]}' is not allowed; specify dataset in {ALLOWED_DATASETS}."
            else:
                return False, f"Invalid table reference '{ref}'."

        return True, None

    def dry_run_check(self, sql: str) -> Tuple[bool, int, Optional[str]]:
        """Executes a dry-run to validate syntax and estimate bytes processed without incurring cost."""
        try:
            dry_job_config = bigquery.QueryJobConfig(
                dry_run=True,
                use_query_cache=False,
                labels=JOB_LABELS,
            )
            job = self.client.query(sql, job_config=dry_job_config)
            bytes_scanned = job.total_bytes_processed or 0
            if bytes_scanned > MAX_BYTES_BILLED:
                return False, bytes_scanned, f"Query would scan {bytes_scanned} bytes, exceeding cap of {MAX_BYTES_BILLED} bytes."
            return True, bytes_scanned, None
        except Exception as e:
            return False, 0, f"Dry-run syntax validation failed: {str(e)}"
