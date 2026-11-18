#!/usr/bin/env python3
"""
Step 4 BigQuery Loader: Load ALL IOCL FY17-FY26 Financial & Downstream 360 Tables + Views
into BOTH un-suffixed (`hrfin_bronze`, `hrfin_silver`, `hrfin_gold`) AND `_v3`
(`hrfin_bronze_v3`, `hrfin_silver_v3`, `hrfin_gold_v3`) datasets in `yukti-finance-iocl`.

Mandatory GCP Attribution:
  - Every LoadJobConfig and QueryJobConfig carries `labels={"datacloud": "jetski"}`.
  - Never touches `ongc-hr-finance-agent`.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from google.cloud import bigquery

PROJECT_ID = os.getenv("TARGET_PROJECT") or "yukti-finance-iocl"
LOCATION = "asia-south1"
ATTRIBUTION_LABELS = {"datacloud": "jetski"}

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "financial_build" / "data"
SSOT_OUT = REPO_ROOT / "financial_ssot" / "out"

assert PROJECT_ID != "ongc-hr-finance-agent", "Safety guardrail: must never touch ongc-hr-finance-agent"


class _BqCliClient:
    """Marker client delegating all BigQuery operations to the authenticated `bq` CLI."""


def _bq_run(args: List[str], *, input_text: Optional[str] = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        args,
        input=input_text,
        text=True,
        capture_output=True,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"bq command failed ({proc.returncode}): {' '.join(args)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return proc


def _ensure_datasets(client: Any) -> None:
    datasets = (
        "hrfin_bronze",
        "hrfin_silver",
        "hrfin_gold",
        "hrfin_gold_staging",
        "hrfin_bronze_v3",
        "hrfin_silver_v3",
        "hrfin_gold_v3",
    )
    if isinstance(client, _BqCliClient):
        for ds_name in datasets:
            chk = _bq_run(["bq", "show", "--format=none", f"{PROJECT_ID}:{ds_name}"], check=False)
            if chk.returncode != 0:
                _bq_run(
                    [
                        "bq",
                        "mk",
                        "--dataset",
                        f"--location={LOCATION}",
                        f"--project_id={PROJECT_ID}",
                        "--label",
                        "datacloud:jetski",
                        f"{PROJECT_ID}:{ds_name}",
                    ]
                )
        return
    for ds_name in datasets:
        ds_ref = bigquery.Dataset(f"{PROJECT_ID}.{ds_name}")
        ds_ref.location = LOCATION
        client.create_dataset(ds_ref, exists_ok=True)


def _run_sql(client: Any, sql: str) -> List[Dict[str, Any]]:
    if isinstance(client, _BqCliClient):
        proc = _bq_run(
            [
                "bq",
                "query",
                "--use_legacy_sql=false",
                f"--project_id={PROJECT_ID}",
                f"--location={LOCATION}",
                "--format=json",
                "--max_rows=100000",
                "--label",
                "datacloud:jetski",
            ],
            input_text=sql,
        )
        out = (proc.stdout or "").strip()
        return json.loads(out) if out.startswith("[") else []
    cfg = bigquery.QueryJobConfig(labels=ATTRIBUTION_LABELS)
    rows = client.query(sql, job_config=cfg).result()
    return [dict(r.items()) for r in rows]


def _cli_num_rows(dataset: str, table: str) -> int:
    proc = _bq_run(["bq", "show", "--format=json", f"{PROJECT_ID}:{dataset}.{table}"])
    info = json.loads((proc.stdout or "{}").strip())
    return int(info.get("numRows", 0))


def _load_parquet(
    client: Any,
    parquet_path: Path,
    dataset: str,
    table: str,
    *,
    time_partitioning_field: Optional[str] = None,
    clustering_fields: Optional[List[str]] = None,
    drop_first: bool = False,
) -> int:
    table_id = f"{PROJECT_ID}.{dataset}.{table}"
    if drop_first:
        _run_sql(client, f"DROP TABLE IF EXISTS `{table_id}`")
    if isinstance(client, _BqCliClient):
        cmd = [
            "bq",
            "load",
            "--replace",
            "--source_format=PARQUET",
            f"--project_id={PROJECT_ID}",
            f"--location={LOCATION}",
            "--label",
            "datacloud:jetski",
        ]
        if time_partitioning_field:
            cmd.extend(["--time_partitioning_type=YEAR", f"--time_partitioning_field={time_partitioning_field}"])
        if clustering_fields:
            cmd.append(f"--clustering_fields={','.join(clustering_fields)}")
        cmd.extend([f"{PROJECT_ID}:{dataset}.{table}", str(parquet_path)])
        _bq_run(cmd)
        return _cli_num_rows(dataset, table)
    cfg = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        labels=ATTRIBUTION_LABELS,
    )
    if time_partitioning_field:
        cfg.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.YEAR,
            field=time_partitioning_field,
        )
    if clustering_fields:
        cfg.clustering_fields = clustering_fields
    with parquet_path.open("rb") as fh:
        client.load_table_from_file(fh, table_id, job_config=cfg).result()
    t = client.get_table(table_id)
    return int(t.num_rows)


def _load_json_rows(
    client: Any,
    rows: List[Dict[str, Any]],
    dataset: str,
    table: str,
    schema: Optional[List[bigquery.SchemaField]] = None,
) -> int:
    if isinstance(client, _BqCliClient):
        with tempfile.TemporaryDirectory(prefix="iocl_bq_load_") as tmpdir:
            tmp = Path(tmpdir)
            ndjson_p = tmp / f"{table}.jsonl"
            ndjson_p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            cmd = [
                "bq",
                "load",
                "--replace",
                "--source_format=NEWLINE_DELIMITED_JSON",
                f"--project_id={PROJECT_ID}",
                f"--location={LOCATION}",
                "--label",
                "datacloud:jetski",
            ]
            if schema is not None:
                schema_p = tmp / f"{table}.schema.json"
                schema_p.write_text(
                    json.dumps(
                        [{"name": f.name, "type": f.field_type, "mode": f.mode or "NULLABLE"} for f in schema],
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                cmd.append(f"--schema={schema_p}")
            else:
                cmd.append("--autodetect")
            cmd.extend([f"{PROJECT_ID}:{dataset}.{table}", str(ndjson_p)])
            _bq_run(cmd)
        return _cli_num_rows(dataset, table)
    table_id = f"{PROJECT_ID}.{dataset}.{table}"
    cfg = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        labels=ATTRIBUTION_LABELS,
    )
    if schema is not None:
        cfg.schema = schema
    else:
        cfg.autodetect = True
    client.load_table_from_json(rows, table_id, job_config=cfg).result()
    t = client.get_table(table_id)
    return int(t.num_rows)


def _create_gold_views(client: bigquery.Client, dataset: str) -> None:
    """Create canonical Gold serving views in `dataset`."""
    _run_sql(
        client,
        f"""
        CREATE OR REPLACE VIEW `{PROJECT_ID}.{dataset}.v_fin_statement_as_reported` AS
        SELECT
          f.*,
          d.display_name,
          d.line_name,
          d.section,
          d.subsection,
          d.level,
          d.hierarchy_level,
          d.display_order,
          d.line_kind,
          d.line_class,
          d.subtotal_formula,
          d.formula,
          d.sign_in_parent,
          d.natural_sign,
          d.schedule3_ref,
          d.ar_note_ref_typical,
          d.xbrl_element_name,
          d.yahoo_field_name,
          d.scope_applicability,
          d.unit_default,
          d.is_subtotal,
          d.is_total,
          d.is_kpi,
          CAST(NULL AS STRING) AS footnote_marker
        FROM `{PROJECT_ID}.{dataset}.fact_financial_statement_line` f
        JOIN `{PROJECT_ID}.{dataset}.dim_financial_line` d
          USING (line_code)
        WHERE f.verified = TRUE
          AND f.period_type = 'annual'
          AND (f.is_own_vintage = TRUE OR f.is_fallback_vintage = TRUE)
        """,
    )
    _run_sql(
        client,
        f"""
        CREATE OR REPLACE VIEW `{PROJECT_ID}.{dataset}.v_fin_trend_latest` AS
        SELECT
          f.*,
          d.display_name,
          d.line_name,
          d.section,
          d.subsection,
          d.level,
          d.hierarchy_level,
          d.display_order,
          d.line_kind,
          d.line_class,
          d.subtotal_formula,
          d.formula,
          d.sign_in_parent,
          d.natural_sign,
          d.schedule3_ref,
          d.ar_note_ref_typical,
          d.xbrl_element_name,
          d.yahoo_field_name,
          d.scope_applicability,
          d.unit_default,
          d.is_subtotal,
          d.is_total,
          d.is_kpi,
          CAST(NULL AS STRING) AS footnote_marker
        FROM `{PROJECT_ID}.{dataset}.fact_financial_statement_line` f
        JOIN `{PROJECT_ID}.{dataset}.dim_financial_line` d
          USING (line_code)
        WHERE f.verified = TRUE
          AND f.period_type = 'annual'
          AND f.is_latest_vintage = TRUE
        """,
    )
    _run_sql(
        client,
        f"""
        CREATE OR REPLACE VIEW `{PROJECT_ID}.{dataset}.v_fin_quarterly_xbrl` AS
        SELECT f.*, d.display_name, d.line_name, d.section, d.subsection, d.level, d.line_kind, d.unit_default, d.is_kpi
        FROM `{PROJECT_ID}.{dataset}.fact_financial_statement_line` f
        JOIN `{PROJECT_ID}.{dataset}.dim_financial_line` d USING (line_code)
        WHERE f.verified = TRUE AND f.period_type = 'quarter'
        """,
    )
    _run_sql(
        client,
        f"""
        CREATE OR REPLACE VIEW `{PROJECT_ID}.{dataset}.v_fin_opening_bs` AS
        SELECT f.*, d.display_name, d.line_name, d.section, d.subsection, d.level, d.line_kind, d.unit_default, d.is_kpi
        FROM `{PROJECT_ID}.{dataset}.fact_financial_statement_line` f
        JOIN `{PROJECT_ID}.{dataset}.dim_financial_line` d USING (line_code)
        WHERE f.verified = TRUE AND f.period_type = 'opening'
        """,
    )
    _run_sql(
        client,
        f"""
        CREATE OR REPLACE VIEW `{PROJECT_ID}.{dataset}.v_fin_yahoo_view` AS
        SELECT
          f.fiscal_year, f.period_type, f.period_end, f.scope, f.statement, f.line_code,
          d.display_name, d.line_name, d.yahoo_field_name, f.value_inr_cr, f.value, f.unit,
          f.report_vintage, f.source_doc, f.source_page
        FROM `{PROJECT_ID}.{dataset}.fact_financial_statement_line` f
        JOIN `{PROJECT_ID}.{dataset}.dim_financial_line` d USING (line_code)
        WHERE f.verified = TRUE AND f.scope = 'consolidated'
        """,
    )
    _run_sql(
        client,
        f"""
        CREATE OR REPLACE VIEW `{PROJECT_ID}.{dataset}.v_fin_coverage` AS
        SELECT
          f.fiscal_year, f.scope, f.period_type, f.statement,
          COUNT(*) AS line_count,
          COUNTIF(f.verified) AS verified_count,
          COUNTIF(f.is_latest_vintage) AS latest_count
        FROM `{PROJECT_ID}.{dataset}.fact_financial_statement_line` f
        GROUP BY 1, 2, 3, 4
        """,
    )
    _run_sql(
        client,
        f"""
        CREATE OR REPLACE VIEW `{PROJECT_ID}.{dataset}.v_refinery_pnl_v3` AS
        SELECT
          r.pnl_id,
          r.fiscal_year,
          r.unit_type,
          r.is_refinery,
          r.refinery_id,
          r.refinery_name,
          r.state,
          r.region,
          r.installed_capacity_mmtpa,
          r.throughput_mmt,
          r.capacity_utilization_pct,
          r.grm_usd_bbl,
          r.opex_usd_bbl,
          r.distillate_yield_pct,
          r.fuel_and_loss_pct,
          r.gross_revenue_inr_cr,
          r.excise_duty_inr_cr,
          r.net_revenue_inr_cr,
          r.other_income_inr_cr,
          r.employee_cost_inr_cr,
          r.crude_and_opex_inr_cr,
          r.ebitda_inr_cr,
          r.dda_inr_cr,
          r.finance_costs_inr_cr,
          r.pbt_pre_exc_inr_cr,
          r.exceptional_items_inr_cr,
          r.pbt_inr_cr,
          r.cpcl_note
        FROM `{PROJECT_ID}.{dataset}.ssot_refinery_economics_360` r
        """,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="IOCL BigQuery SSOT Loader")
    parser.add_argument("--bq-cli", action="store_true", help="Delegate BigQuery operations to authenticated `bq` CLI")
    args = parser.parse_args()
    client: Any = _BqCliClient() if args.bq_cli else bigquery.Client(project=PROJECT_ID, location=LOCATION)
    _ensure_datasets(client)

    cw_rows = json.loads((DATA_DIR / "iocl_10yr_corporate_wide.json").read_text())
    pnl_rows = json.loads((DATA_DIR / "iocl_10yr_schedule_iii_lines.json").read_text())
    bs_rows = json.loads((DATA_DIR / "iocl_10yr_balance_sheet_lines.json").read_text())
    cf_rows = json.loads((DATA_DIR / "iocl_10yr_cash_flow_lines.json").read_text())
    ratio_rows = json.loads((DATA_DIR / "iocl_10yr_ratios_lines.json").read_text())
    ref_rows = json.loads((DATA_DIR / "ssot_refinery_economics_360.json").read_text())

    # 1. Staging gate on hrfin_gold_staging
    _load_parquet(client, SSOT_OUT / "dim_financial_line.parquet", "hrfin_gold_staging", "dim_financial_line", clustering_fields=["statement", "section"])
    _load_parquet(
        client,
        SSOT_OUT / "fact_snapshot.parquet",
        "hrfin_gold_staging",
        "fact_financial_statement_line",
        time_partitioning_field="period_end",
        clustering_fields=["scope", "statement", "line_code"],
        drop_first=True,
    )
    _load_parquet(client, SSOT_OUT / "fact_financial_line_conflict.parquet", "hrfin_gold_staging", "fact_financial_line_conflict")
    _load_parquet(client, SSOT_OUT / "fin_gate_run.parquet", "hrfin_gold_staging", "fin_gate_run")
    _load_parquet(client, SSOT_OUT / "ssot_refinery_economics_360.parquet", "hrfin_gold_staging", "ssot_refinery_economics_360")
    _create_gold_views(client, "hrfin_gold_staging")

    dup_check = _run_sql(
        client,
        f"""
        SELECT COUNT(*) AS dup_n FROM (
          SELECT fiscal_year, scope, line_code
          FROM `{PROJECT_ID}.hrfin_gold_staging.v_fin_trend_latest`
          GROUP BY 1, 2, 3 HAVING COUNT(*) > 1
        )
        """,
    )
    assert int(dup_check[0]["dup_n"]) == 0, f"Duplicate keys in staging v_fin_trend_latest: {dup_check}"

    stmt_schema = [
        bigquery.SchemaField("fiscal_year", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("line_order", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("line_code", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("line_name", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("section", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("schedule_ref", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("amount_inr_cr", "FLOAT64", mode="REQUIRED"),
        bigquery.SchemaField("prior_fy_amount_inr_cr", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("yoy_delta_inr_cr", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("yoy_change_pct", "FLOAT64", mode="NULLABLE"),
    ]
    ratio_schema = [
        bigquery.SchemaField("fiscal_year", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("line_order", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("line_code", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("ratio_name", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("category", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("unit", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("formula", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("value", "FLOAT64", mode="REQUIRED"),
        bigquery.SchemaField("prior_fy_value", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("yoy_delta", "FLOAT64", mode="NULLABLE"),
    ]

    # 2. Load Gold + Gold v3 datasets
    summary: Dict[str, Any] = {}
    for gold_ds in ("hrfin_gold", "hrfin_gold_v3"):
        summary[f"{gold_ds}.dim_financial_line"] = _load_parquet(
            client, SSOT_OUT / "dim_financial_line.parquet", gold_ds, "dim_financial_line", clustering_fields=["statement", "section"]
        )
        summary[f"{gold_ds}.fact_financial_statement_line"] = _load_parquet(
            client,
            SSOT_OUT / "fact_snapshot.parquet",
            gold_ds,
            "fact_financial_statement_line",
            time_partitioning_field="period_end",
            clustering_fields=["scope", "statement", "line_code"],
            drop_first=True,
        )
        summary[f"{gold_ds}.fact_financial_line_conflict"] = _load_parquet(
            client, SSOT_OUT / "fact_financial_line_conflict.parquet", gold_ds, "fact_financial_line_conflict"
        )
        summary[f"{gold_ds}.fin_gate_run"] = _load_parquet(
            client, SSOT_OUT / "fin_gate_run.parquet", gold_ds, "fin_gate_run"
        )
        summary[f"{gold_ds}.ssot_corporate_annual_360"] = _load_json_rows(client, cw_rows, gold_ds, "ssot_corporate_annual_360")
        summary[f"{gold_ds}.ssot_corporate_pnl_lines"] = _load_json_rows(
            client, pnl_rows, gold_ds, "ssot_corporate_pnl_lines",
            schema=stmt_schema + [bigquery.SchemaField("pct_of_revenue", "FLOAT64", mode="NULLABLE"), bigquery.SchemaField("driver_note", "STRING", mode="NULLABLE")],
        )
        summary[f"{gold_ds}.ssot_corporate_balance_sheet_lines"] = _load_json_rows(
            client, bs_rows, gold_ds, "ssot_corporate_balance_sheet_lines",
            schema=stmt_schema + [bigquery.SchemaField("pct_of_total_assets", "FLOAT64", mode="NULLABLE"), bigquery.SchemaField("driver_note", "STRING", mode="NULLABLE")],
        )
        summary[f"{gold_ds}.ssot_corporate_cash_flow_lines"] = _load_json_rows(
            client, cf_rows, gold_ds, "ssot_corporate_cash_flow_lines",
            schema=stmt_schema + [bigquery.SchemaField("pct_of_ocf", "FLOAT64", mode="NULLABLE"), bigquery.SchemaField("driver_note", "STRING", mode="NULLABLE")],
        )
        summary[f"{gold_ds}.ssot_corporate_ratios_lines"] = _load_json_rows(
            client, ratio_rows, gold_ds, "ssot_corporate_ratios_lines", schema=ratio_schema,
        )
        summary[f"{gold_ds}.ssot_refinery_economics_360"] = _load_parquet(
            client, SSOT_OUT / "ssot_refinery_economics_360.parquet", gold_ds, "ssot_refinery_economics_360",
            clustering_fields=["fiscal_year", "unit_type", "refinery_id"],
        )
        summary[f"{gold_ds}.fact_marketing_sales"] = _load_parquet(
            client, SSOT_OUT / "fact_marketing_sales.parquet", gold_ds, "fact_marketing_sales",
            clustering_fields=["fiscal_year", "product_code"],
        )
        summary[f"{gold_ds}.fact_pipeline_ops"] = _load_parquet(
            client, SSOT_OUT / "fact_pipeline_ops.parquet", gold_ds, "fact_pipeline_ops",
            clustering_fields=["fiscal_year", "pipeline_code"],
        )
        summary[f"{gold_ds}.fact_segment"] = _load_parquet(
            client, SSOT_OUT / "fact_segment.parquet", gold_ds, "fact_segment",
            clustering_fields=["fiscal_year", "segment_code", "metric"],
        )
        summary[f"{gold_ds}.fact_mou_scorecard"] = _load_parquet(
            client, SSOT_OUT / "fact_mou_scorecard.parquet", gold_ds, "fact_mou_scorecard",
            clustering_fields=["fiscal_year", "parameter_id"],
        )
        summary[f"{gold_ds}.recon_checks"] = _load_parquet(
            client, SSOT_OUT / "recon_checks.parquet", gold_ds, "recon_checks",
            clustering_fields=["domain", "fiscal_year", "status"],
        )
        if (SSOT_OUT / "fact_retail_fuel_prices.parquet").exists():
            summary[f"{gold_ds}.fact_retail_fuel_prices"] = _load_parquet(
                client, SSOT_OUT / "fact_retail_fuel_prices.parquet", gold_ds, "fact_retail_fuel_prices",
                clustering_fields=["fiscal_year", "fuel_code", "city"],
            )
        if (SSOT_OUT / "fact_fuel_price_buildup.parquet").exists():
            summary[f"{gold_ds}.fact_fuel_price_buildup"] = _load_parquet(
                client, SSOT_OUT / "fact_fuel_price_buildup.parquet", gold_ds, "fact_fuel_price_buildup",
                clustering_fields=["fiscal_year", "fuel_code", "city"],
            )
        _create_gold_views(client, gold_ds)

    # 3. Load Silver + Silver v3 datasets
    ref_only_rows = [r for r in ref_rows if r["unit_type"] == "REFINERY"]
    for silver_ds in ("hrfin_silver", "hrfin_silver_v3"):
        summary[f"{silver_ds}.corporate_financials"] = _load_json_rows(client, cw_rows, silver_ds, "corporate_financials")
        summary[f"{silver_ds}.refinery_pnl_annual"] = _load_json_rows(client, ref_only_rows, silver_ds, "refinery_pnl_annual")
        summary[f"{silver_ds}.subsidiary_financials"] = _load_parquet(
            client, SSOT_OUT / "subsidiary_financials.parquet", silver_ds, "subsidiary_financials",
            clustering_fields=["fiscal_year", "entity_code"],
        )
        summary[f"{silver_ds}.marketing_sales_annual"] = _load_parquet(
            client, SSOT_OUT / "fact_marketing_sales.parquet", silver_ds, "marketing_sales_annual"
        )
        summary[f"{silver_ds}.pipeline_ops_annual"] = _load_parquet(
            client, SSOT_OUT / "fact_pipeline_ops.parquet", silver_ds, "pipeline_ops_annual"
        )
        summary[f"{silver_ds}.recon_checks"] = _load_parquet(
            client, SSOT_OUT / "recon_checks.parquet", silver_ds, "recon_checks"
        )

    # 4. Load Bronze + Bronze v3 datasets
    snap_df = pd.read_parquet(SSOT_OUT / "fact_snapshot.parquet")
    bronze_rows = [
        {
            "extract_id": str(r["extract_id"]),
            "source_system": str(r["source_system"]),
            "source_doc": str(r["source_doc"]),
            "source_page": int(r["source_page"]),
            "source_page_label": str(r["source_page_label"]),
            "source_text_line": int(r["source_text_line"]),
            "raw_label": str(r["raw_label"]),
            "raw_value_text": str(r["raw_value_text"]),
            "parsed_value": float(r["value_native"]),
            "unit": str(r["unit_native"]),
            "column_header": str(r["fiscal_year"]),
            "scope": str(r["scope"]),
            "statement_guess": str(r["statement"]),
            "extractor_version": str(r["extractor_version"]),
            "extracted_at": str(r["extracted_at"]),
        }
        for _, r in snap_df.iterrows()
    ]
    bronze_ref = [
        {
            "fiscal_year": r["fiscal_year"],
            "refinery_id": r["refinery_id"],
            "refinery_name": r["refinery_name"],
            "installed_capacity_mmtpa": r["installed_capacity_mmtpa"],
            "throughput_mmt": r["throughput_mmt"],
            "grm_usd_bbl": r["grm_usd_bbl"],
            "source_system": "annual_report_and_ppac",
            "extracted_at": "2026-11-16T00:00:00Z",
        }
        for r in ref_only_rows
    ]
    for bronze_ds in ("hrfin_bronze", "hrfin_bronze_v3"):
        summary[f"{bronze_ds}.fin_extract_raw"] = _load_json_rows(client, bronze_rows, bronze_ds, "fin_extract_raw")
        summary[f"{bronze_ds}.raw_refinery_throughput"] = _load_json_rows(client, bronze_ref, bronze_ds, "raw_refinery_throughput")

    print(json.dumps({"project": PROJECT_ID, "location": LOCATION, "loaded_tables": summary}, indent=2))


if __name__ == "__main__":
    main()
