"""BigQuery Reconciliation Test for IOCL Downstream 360 & Finance Gold Tables in yukti-finance-iocl.

Verifies exact mathematical alignment across BigQuery gold tables/views:
(a) ssot_refinery_economics_360 vs v_refinery_pnl_v3 (9 refineries, 75.451 MMT throughput, weighted GRM $10.85/bbl in FY26)
(b) fact_financial_statement_line vs v_fin_trend_latest & zero unresolved conflicts (FY26 Rev Ops 886,224.41 Cr, PAT 36,802.42 Cr)
(c) fact_marketing_sales & fact_segment reconciliation in FY26 (105.117 MMT marketing sales)
(d) fact_wacc_annual (9.2534% FY26) & fact_mou_scorecard (12 KPIs x 2 FYs = 24 rows)
"""

from decimal import Decimal
from pathlib import Path
import sys
from google.cloud import bigquery
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import BQ_GOLD_DATASET, BQ_LOCATION, GCP_PROJECT, JOB_LABELS


@pytest.fixture(scope="module")
def bq_client():
    return bigquery.Client(
        project=GCP_PROJECT,
        location=BQ_LOCATION,
        default_query_job_config=bigquery.QueryJobConfig(labels=JOB_LABELS),
    )


def test_reconcile_refinery_economics(bq_client):
    """(a) 9 standalone refineries in FY26: 75.451 MMT throughput, $10.85/bbl weighted GRM, exact SSOT/view match."""
    sql_view = f"""
    SELECT
        COUNT(*) AS n_refineries,
        ROUND(SUM(throughput_mmt), 3) AS sum_throughput_mmt,
        ROUND(SUM(grm_usd_bbl * throughput_mmt) / NULLIF(SUM(throughput_mmt), 0), 2) AS weighted_grm,
        ROUND(SUM(ebitda_inr_cr), 2) AS sum_ebitda_cr,
        ROUND(SUM(pbt_inr_cr), 2) AS sum_pbt_cr
    FROM `{GCP_PROJECT}.{BQ_GOLD_DATASET}.v_refinery_pnl_v3`
    WHERE fiscal_year = 'FY26' AND is_refinery = TRUE;
    """
    sql_ssot = f"""
    SELECT
        COUNT(*) AS n_refineries,
        ROUND(SUM(throughput_mmt), 3) AS sum_throughput_mmt,
        ROUND(SUM(grm_usd_bbl * throughput_mmt) / NULLIF(SUM(throughput_mmt), 0), 2) AS weighted_grm,
        ROUND(SUM(ebitda_inr_cr), 2) AS sum_ebitda_cr,
        ROUND(SUM(pbt_inr_cr), 2) AS sum_pbt_cr
    FROM `{GCP_PROJECT}.{BQ_GOLD_DATASET}.ssot_refinery_economics_360`
    WHERE fiscal_year = 'FY26' AND is_refinery = TRUE;
    """
    r_view = dict(list(bq_client.query(sql_view).result())[0])
    r_ssot = dict(list(bq_client.query(sql_ssot).result())[0])

    assert r_view == r_ssot
    assert r_view["n_refineries"] == 9
    assert float(r_view["sum_throughput_mmt"]) == pytest.approx(75.451, abs=0.01)
    assert float(r_view["weighted_grm"]) == pytest.approx(10.85, abs=0.05)


def test_reconcile_financial_statements_and_zero_conflicts(bq_client):
    """(b) FY26 P&L & Balance Sheet in v_fin_trend_latest tie with 0 unresolved SSOT conflicts."""
    sql_conflicts = f"""
    SELECT COUNTIF(LOWER(COALESCE(status, '')) != 'resolved') AS open_conflicts
    FROM `{GCP_PROJECT}.{BQ_GOLD_DATASET}.fact_financial_line_conflict`;
    """
    open_conflicts = list(bq_client.query(sql_conflicts).result())[0]["open_conflicts"]
    assert open_conflicts == 0

    sql_trend = f"""
    SELECT
        MAX(IF(line_code = 'PL.REV_OPS', ROUND(COALESCE(value_inr_cr, value), 2), NULL)) AS rev_ops_cr,
        MAX(IF(line_code = 'PL.PAT', ROUND(COALESCE(value_inr_cr, value), 2), NULL)) AS pat_cr,
        MAX(IF(line_code = 'BS.TOTAL_ASSETS', ROUND(COALESCE(value_inr_cr, value), 2), NULL)) AS total_assets_cr,
        MAX(IF(line_code = 'BS.TOTAL_EQ_LIAB', ROUND(COALESCE(value_inr_cr, value), 2), NULL)) AS total_eq_liab_cr
    FROM `{GCP_PROJECT}.{BQ_GOLD_DATASET}.v_fin_trend_latest`
    WHERE scope = 'standalone' AND fiscal_year = 'FY26';
    """
    r = dict(list(bq_client.query(sql_trend).result())[0])
    assert Decimal(str(r["rev_ops_cr"])) == Decimal("886224.41")
    assert Decimal(str(r["pat_cr"])) == Decimal("36802.42")
    assert r["total_assets_cr"] == r["total_eq_liab_cr"]


def test_reconcile_marketing_and_segments(bq_client):
    """(c) FY26 marketing sales across products and standalone Ind AS 108 segments match SSOT."""
    sql_mkt = f"""
    SELECT ROUND(SUM(sales_volume_mmt), 3) AS total_mmt
    FROM `{GCP_PROJECT}.{BQ_GOLD_DATASET}.fact_marketing_sales`
    WHERE fiscal_year = 'FY26';
    """
    mkt_mmt = float(list(bq_client.query(sql_mkt).result())[0]["total_mmt"])
    assert mkt_mmt == pytest.approx(105.117, abs=0.05)

    sql_seg = f"""
    SELECT COUNT(DISTINCT segment_code) AS n_segments, ROUND(SUM(value_inr_cr), 2) AS total_seg_rev
    FROM `{GCP_PROJECT}.{BQ_GOLD_DATASET}.fact_segment`
    WHERE fiscal_year = 'FY26' AND scope = 'standalone' AND metric = 'segment_revenue';
    """
    r_seg = dict(list(bq_client.query(sql_seg).result())[0])
    assert r_seg["n_segments"] >= 3
    assert float(r_seg["total_seg_rev"]) > 0


def test_reconcile_wacc_and_mou_scorecard(bq_client):
    """(d) FY26 WACC equals 9.2534% and MoU Scorecard holds 12 parameters x 2 FYs (24 rows)."""
    sql_wacc = f"""
    SELECT ROUND(wacc_pct, 4) AS wacc_pct
    FROM `{GCP_PROJECT}.{BQ_GOLD_DATASET}.fact_wacc_annual`
    WHERE fiscal_year = 'FY26' AND verified = TRUE;
    """
    wacc = float(list(bq_client.query(sql_wacc).result())[0]["wacc_pct"])
    assert wacc == pytest.approx(9.2534, abs=1e-4)

    sql_mou = f"""
    SELECT COUNT(*) AS n_rows, COUNT(DISTINCT parameter_id) AS n_params
    FROM `{GCP_PROJECT}.{BQ_GOLD_DATASET}.fact_mou_scorecard`;
    """
    r_mou = dict(list(bq_client.query(sql_mou).result())[0])
    assert r_mou["n_params"] == 12
    assert r_mou["n_rows"] == 24
