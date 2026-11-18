"""Parameterized What-If Scenario Engine for Yukti IOCL.

Implements executive what-if simulations over live BigQuery data (`yukti-finance-iocl`):
1. GRM ($/bbl) Sensitivity: Evaluates annualized EBITDA & PAT impact across 9 IOCL refineries
   (`hrfin_gold.ssot_refinery_economics_360`) for a target GRM or +$1.50/bbl improvement.
2. Brent / Feedstock Shock: Models refining margin and inventory holding sensitivity at custom Brent $/bbl.
3. USD/INR FX Sensitivity: Models crude import bill & debt service impact of ₹3/USD (or custom) depreciation.
4. Retail Auto-Fuel Marketing Margin: Models ₹0.50/litre MS/HSD marketing margin change over `fact_marketing_sales`.
"""

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from google.cloud import bigquery

from app.config import BQ_LOCATION, GCP_PROJECT, JOB_LABELS

logger = logging.getLogger("yukti.tools.what_if")


def run_what_if_simulation(
    scenario: str,
    brent_price: Optional[float] = 60.0,
    freeze_months: Optional[int] = 24,
    relocated_officers: Optional[int] = 200,
    cta_lakh: Optional[float] = 3.25,
    persona: str = "CMD",
) -> Dict[str, Any]:
    """Runs a live parameterized IOCL Downstream What-If simulation on BigQuery."""
    t0 = time.perf_counter()
    from app.config import YUKTI_RESULT_CACHE
    from app.tool_cache import get_tool_cache

    tool_cache = get_tool_cache()
    params = {
        "brent_price": brent_price,
        "freeze_months": freeze_months,
        "relocated_officers": relocated_officers,
        "cta_lakh": cta_lakh,
    }

    if YUKTI_RESULT_CACHE:
        cached = tool_cache.get_whatif(scenario, params, persona=persona)
        if cached:
            cached_copy = dict(cached)
            cached_copy["from_cache"] = True
            cached_copy["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            return cached_copy

    scen = (scenario or "").lower()
    client = bigquery.Client(project=GCP_PROJECT, location=BQ_LOCATION)

    # Extract optional custom GRM delta / FX shock / retail ₹/L delta from scenario string
    grm_match = re.search(
        r"(?:grm|margin|improves?\s+by|expands?\s+by|changes?\s+by|drops?\s+by)\D{0,25}\$?\s*([+-]?\d+(?:\.\d+)?)\s*(?:/bbl|usd/bbl|per\s*bbl|\$/bbl)?|([+-]?\d+(?:\.\d+)?)\s*(?:\$/bbl|usd/bbl|per\s*bbl|grm)",
        scen,
    )
    fx_match = re.search(r"(?:rs\.?|inr|₹)\s*(\d+(?:\.\d+)?)", scen)

    mode = "brent"
    if any(k in scen for k in ("grm", "crack", "refin")):
        mode = "grm"
    elif any(k in scen for k in ("fx", "rupee", "depreciat", "usd", "exchange rate", "inr")):
        mode = "fx"
    elif any(k in scen for k in ("retail", "auto-fuel", "auto fuel", "marketing margin", "petrol", "diesel", "litre", "liter")):
        mode = "retail"

    if mode == "grm":
        delta_grm = float(grm_match.group(1) or grm_match.group(2)) if grm_match else 1.50
        sql = f"""SELECT
    refinery_id,
    refinery_name,
    region,
    ROUND(throughput_mmt, 3) AS throughput_mmt,
    ROUND(grm_usd_bbl, 2) AS base_grm_usd_bbl,
    ROUND(grm_usd_bbl + {delta_grm}, 2) AS sim_grm_usd_bbl,
    ROUND(ebitda_inr_cr, 2) AS base_ebitda_inr_cr,
    ROUND(ebitda_inr_cr + (throughput_mmt * 7.33 * {delta_grm} * 88.37 / 10.0), 2) AS sim_ebitda_inr_cr,
    ROUND(throughput_mmt * 7.33 * {delta_grm} * 88.37 / 10.0, 2) AS delta_ebitda_inr_cr,
    ROUND((throughput_mmt * 7.33 * {delta_grm} * 88.37 / 10.0) * (1.0 - 0.2517), 2) AS delta_pat_inr_cr,
    FALSE AS is_ebitda_negative,
    FALSE AS is_pbt_negative
FROM `{GCP_PROJECT}.hrfin_gold.ssot_refinery_economics_360`
WHERE fiscal_year = 'FY26' AND is_refinery = TRUE
ORDER BY delta_ebitda_inr_cr DESC;"""
    elif mode == "fx":
        fx_delta = float(fx_match.group(1)) if fx_match and float(fx_match.group(1)) < 20 else 3.0
        sql = f"""SELECT
    fiscal_year,
    ROUND(fx_inr_per_usd, 2) AS base_fx_inr_per_usd,
    ROUND(fx_inr_per_usd + {fx_delta}, 2) AS shocked_fx_inr_per_usd,
    ROUND(cost_of_materials_consumed_inr_cr, 2) AS base_crude_import_bill_cr,
    ROUND(cost_of_materials_consumed_inr_cr * ({fx_delta} / NULLIF(fx_inr_per_usd, 0)), 2) AS gross_import_bill_increase_cr,
    ROUND(finance_costs_inr_cr, 2) AS base_finance_cost_cr,
    ROUND(pbt_inr_cr, 2) AS base_pbt_inr_cr,
    FALSE AS is_ebitda_negative,
    FALSE AS is_pbt_negative
FROM `{GCP_PROJECT}.hrfin_gold.ssot_corporate_annual_360`
WHERE fiscal_year IN ('FY24', 'FY25', 'FY26')
ORDER BY fiscal_year DESC;"""
    elif mode == "retail":
        rs_per_litre = -float(fx_match.group(1)) if fx_match else -0.50
        if "improv" in scen or "increas" in scen or "+" in scen:
            rs_per_litre = abs(rs_per_litre)
        sql = f"""SELECT
    product_code,
    product_category,
    ROUND(sales_volume_mmt, 3) AS sales_volume_mmt,
    ROUND(gross_marketing_margin_inr_kl, 0) AS base_margin_inr_kl,
    ROUND({rs_per_litre} * 1000.0, 0) AS margin_shock_inr_kl,
    ROUND(sales_volume_mmt * 1.25 * ({rs_per_litre} * 1000.0) / 10.0, 2) AS annualized_ebitda_impact_cr,
    FALSE AS is_ebitda_negative,
    FALSE AS is_pbt_negative
FROM `{GCP_PROJECT}.hrfin_gold.fact_marketing_sales`
WHERE fiscal_year = 'FY26' AND product_code IN ('MS', 'HSD', 'ATF', 'LPG')
ORDER BY ABS(sales_volume_mmt) DESC;"""
    else:
        try:
            price = float(brent_price) if brent_price is not None and float(brent_price) > 0 else 60.0
        except Exception:
            price = 60.0
        # Inventory + refining spread sensitivity around FY26 base Brent ($69.04/bbl)
        sql = f"""SELECT
    refinery_id,
    refinery_name,
    region,
    ROUND(throughput_mmt, 3) AS throughput_mmt,
    ROUND(grm_usd_bbl, 2) AS base_grm_usd_bbl,
    ROUND(net_revenue_inr_cr, 2) AS base_net_revenue_inr_cr,
    ROUND(net_revenue_inr_cr * ({price} / 69.04), 2) AS sim_net_revenue_inr_cr,
    ROUND(ebitda_inr_cr + (throughput_mmt * 7.33 * (({price} - 69.04) * 0.06) * 88.37 / 10.0), 2) AS sim_ebitda_inr_cr,
    ROUND(pbt_inr_cr + (throughput_mmt * 7.33 * (({price} - 69.04) * 0.06) * 88.37 / 10.0), 2) AS sim_pbt_inr_cr,
    (ebitda_inr_cr + (throughput_mmt * 7.33 * (({price} - 69.04) * 0.06) * 88.37 / 10.0)) < 0 AS is_ebitda_negative,
    (pbt_inr_cr + (throughput_mmt * 7.33 * (({price} - 69.04) * 0.06) * 88.37 / 10.0)) < 0 AS is_pbt_negative
FROM `{GCP_PROJECT}.hrfin_gold.ssot_refinery_economics_360`
WHERE fiscal_year = 'FY26' AND is_refinery = TRUE
ORDER BY sim_pbt_inr_cr DESC;"""

    try:
        from app.config import rewrite_dataset_sql

        sql_exec = rewrite_dataset_sql(sql)
        job = client.query(sql_exec, job_config=bigquery.QueryJobConfig(labels=JOB_LABELS))
        res = job.result()
        columns = [f.name for f in res.schema] if res.schema else []
        clean_rows: List[Dict[str, Any]] = []
        for r in res:
            clean_r = {}
            for k, v in dict(r).items():
                if hasattr(v, "isoformat"):
                    clean_r[k] = v.isoformat()
                elif hasattr(v, "__float__"):
                    try:
                        clean_r[k] = float(v)
                    except Exception:
                        clean_r[k] = str(v)
                else:
                    clean_r[k] = v
            clean_rows.append(clean_r)

        out = {
            "status": "success",
            "scenario": scenario,
            "simulated_brent_price": price if "price" in locals() else None,
            "sql": sql_exec,
            "row_count": len(clean_rows),
            "columns": columns,
            "rows": clean_rows[:25],
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
        }
        if YUKTI_RESULT_CACHE:
            tool_cache.set_whatif(scenario, params, persona, out)
        return out
    except Exception as e:
        if os.getenv("YUKTI_FORCE_BQ_FAIL", "0") not in ("1", "true", "yes"):
            fb_rows = _local_what_if_fallback(mode, scen, locals())
            if fb_rows:
                out = {
                    "status": "success",
                    "scenario": scenario,
                    "simulated_brent_price": price if "price" in locals() else None,
                    "sql": sql,
                    "row_count": len(fb_rows),
                    "columns": list(fb_rows[0].keys()),
                    "rows": fb_rows[:25],
                    "source": "local_snapshot",
                    "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
                }
                if YUKTI_RESULT_CACHE:
                    tool_cache.set_whatif(scenario, params, persona, out)
                return out
        logger.exception(f"Error executing what-if simulation: {e}")
        return {
            "status": "error",
            "error": str(e),
            "sql": sql,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
        }


def _local_what_if_fallback(mode: str, scen: str, local_vars: Dict[str, Any]) -> List[Dict[str, Any]]:
    data_dir = Path(__file__).resolve().parents[4] / "financial_build" / "data"
    fb_rows: List[Dict[str, Any]] = []
    try:
        if mode == "grm" and (data_dir / "ssot_refinery_economics_360.json").exists():
            delta_grm = float(local_vars.get("delta_grm", 1.50))
            rows = json.loads((data_dir / "ssot_refinery_economics_360.json").read_text(encoding="utf-8"))
            for r in rows:
                if r.get("fiscal_year") == "FY26" and r.get("is_refinery"):
                    tp = float(r.get("throughput_mmt") or 0.0)
                    eb = float(r.get("ebitda_inr_cr") or 0.0)
                    d_eb = round(tp * 7.33 * delta_grm * 88.37 / 10.0, 2)
                    fb_rows.append({
                        "refinery_id": r["refinery_id"],
                        "refinery_name": r["refinery_name"],
                        "region": r.get("region"),
                        "throughput_mmt": round(tp, 3),
                        "base_grm_usd_bbl": round(float(r.get("grm_usd_bbl") or 0.0), 2),
                        "sim_grm_usd_bbl": round(float(r.get("grm_usd_bbl") or 0.0) + delta_grm, 2),
                        "base_ebitda_inr_cr": round(eb, 2),
                        "sim_ebitda_inr_cr": round(eb + d_eb, 2),
                        "delta_ebitda_inr_cr": d_eb,
                        "delta_pat_inr_cr": round(d_eb * (1.0 - 0.2517), 2),
                        "is_ebitda_negative": False,
                        "is_pbt_negative": False,
                    })
            fb_rows.sort(key=lambda x: -x["delta_ebitda_inr_cr"])
        elif mode == "fx" and (data_dir / "iocl_10yr_corporate_wide.json").exists():
            fx_delta = float(local_vars.get("fx_delta", 3.0))
            rows = json.loads((data_dir / "iocl_10yr_corporate_wide.json").read_text(encoding="utf-8"))
            for r in sorted(rows, key=lambda x: x.get("fiscal_year", ""), reverse=True):
                if r.get("fiscal_year") in ("FY24", "FY25", "FY26"):
                    fx = float(r.get("fx_inr_per_usd") or 88.37)
                    raw = float(r.get("cost_of_materials_consumed_inr_cr") or 0.0)
                    fb_rows.append({
                        "fiscal_year": r["fiscal_year"],
                        "base_fx_inr_per_usd": round(fx, 2),
                        "shocked_fx_inr_per_usd": round(fx + fx_delta, 2),
                        "base_crude_import_bill_cr": round(raw, 2),
                        "gross_import_bill_increase_cr": round(raw * (fx_delta / fx), 2),
                        "base_finance_cost_cr": round(float(r.get("finance_costs_inr_cr") or 0.0), 2),
                        "base_pbt_inr_cr": round(float(r.get("pbt_inr_cr") or 0.0), 2),
                        "is_ebitda_negative": False,
                        "is_pbt_negative": False,
                    })
        elif mode == "retail" and (data_dir / "fact_marketing_sales.json").exists():
            rs_l = float(local_vars.get("rs_per_litre", -0.50))
            rows = json.loads((data_dir / "fact_marketing_sales.json").read_text(encoding="utf-8"))
            for r in rows:
                if r.get("fiscal_year") == "FY26" and r.get("product_code") in ("MS", "HSD", "ATF", "LPG"):
                    vol = float(r.get("sales_volume_mmt") or 0.0)
                    fb_rows.append({
                        "product_code": r["product_code"],
                        "product_category": r.get("product_category"),
                        "sales_volume_mmt": round(vol, 3),
                        "base_margin_inr_kl": round(float(r.get("gross_marketing_margin_inr_kl") or 0.0), 0),
                        "margin_shock_inr_kl": round(rs_l * 1000.0, 0),
                        "annualized_ebitda_impact_cr": round(vol * 1.25 * (rs_l * 1000.0) / 10.0, 2),
                        "is_ebitda_negative": False,
                        "is_pbt_negative": False,
                    })
        elif (data_dir / "ssot_refinery_economics_360.json").exists():
            price = float(local_vars.get("price", 60.0))
            rows = json.loads((data_dir / "ssot_refinery_economics_360.json").read_text(encoding="utf-8"))
            for r in rows:
                if r.get("fiscal_year") == "FY26" and r.get("is_refinery"):
                    tp = float(r.get("throughput_mmt") or 0.0)
                    eb = float(r.get("ebitda_inr_cr") or 0.0)
                    pbt = float(r.get("pbt_inr_cr") or 0.0)
                    nr = float(r.get("net_revenue_inr_cr") or 0.0)
                    adj = tp * 7.33 * ((price - 69.04) * 0.06) * 88.37 / 10.0
                    fb_rows.append({
                        "refinery_id": r["refinery_id"],
                        "refinery_name": r["refinery_name"],
                        "region": r.get("region"),
                        "throughput_mmt": round(tp, 3),
                        "base_grm_usd_bbl": round(float(r.get("grm_usd_bbl") or 0.0), 2),
                        "base_net_revenue_inr_cr": round(nr, 2),
                        "sim_net_revenue_inr_cr": round(nr * (price / 69.04), 2),
                        "sim_ebitda_inr_cr": round(eb + adj, 2),
                        "sim_pbt_inr_cr": round(pbt + adj, 2),
                        "is_ebitda_negative": (eb + adj) < 0,
                        "is_pbt_negative": (pbt + adj) < 0,
                    })
            fb_rows.sort(key=lambda x: -x["sim_pbt_inr_cr"])
    except Exception:
        return []
    return fb_rows
