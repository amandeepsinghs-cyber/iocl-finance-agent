#!/usr/bin/env python3
"""
Step 6.1 Semantic Catalog & Entities Generator for Yukti IOCL:
  1. Queries live `yukti-finance-iocl` BigQuery `hrfin_gold.*` and `hrfin_silver.*`
     schemas and distinct categorical values (`labels={"datacloud": "jetski"}`),
     writing `yukti/backend/app/semantic/semantic_catalog.json`.
  2. Writes IOCL-native `yukti/backend/app/semantic/entities.json` (9 Refineries,
     Divisions/Offices, Subsidiaries, Marketing Products, Pipelines, Segments,
     Finance/Downstream Disciplines, Grades A-I + E1-E9 compat; 0 HR/Upstream fields).
  3. Writes IOCL-native `yukti/backend/app/semantic/entity_aliases.yaml`.
"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import yaml
from google.cloud import bigquery

PROJECT_ID = os.getenv("TARGET_PROJECT") or os.getenv("YUKTI_GCP_PROJECT") or "yukti-finance-iocl"
BQ_LOCATION = "asia-south1"
ATTRIBUTION_LABELS = {"datacloud": "jetski"}

assert PROJECT_ID != "ongc-hr-finance-agent", "Guardrail: must never target ONGC project"

REPO_ROOT = Path(__file__).resolve().parents[2]
SEM_DIR = REPO_ROOT / "yukti" / "backend" / "app" / "semantic"


def build_catalog(bq: bigquery.Client) -> Dict[str, Any]:
    tables_out: Dict[str, Any] = {}
    for ds in ("hrfin_gold", "hrfin_silver"):
        tbl_rows = list(
            bq.query(
                f"SELECT table_name, table_type FROM `{PROJECT_ID}.{ds}.INFORMATION_SCHEMA.TABLES` ORDER BY table_name",
                job_config=bigquery.QueryJobConfig(labels=ATTRIBUTION_LABELS),
            ).result()
        )
        col_rows = list(
            bq.query(
                f"SELECT table_name, column_name, data_type FROM `{PROJECT_ID}.{ds}.INFORMATION_SCHEMA.COLUMNS` ORDER BY table_name, ordinal_position",
                job_config=bigquery.QueryJobConfig(labels=ATTRIBUTION_LABELS),
            ).result()
        )
        cols_by_tbl: Dict[str, List[tuple[str, str]]] = {}
        for cr in col_rows:
            cols_by_tbl.setdefault(cr.table_name, []).append((cr.column_name, cr.data_type))

        for tr in tbl_rows:
            tname = tr.table_name
            full_key = f"{ds}.{tname}"
            col_meta: Dict[str, Any] = {}
            tcols = cols_by_tbl.get(tname, [])

            # Inspect sample/profiled distinct values for STRING columns cleanly in one pass
            string_cols = [c for c, dt in tcols if dt == "STRING"]
            num_cols = [c for c, dt in tcols if dt in ("FLOAT64", "INT64", "NUMERIC", "BIGNUMERIC")]
            bool_cols = [c for c, dt in tcols if dt == "BOOL"]

            for c, dt in tcols:
                norm_dt = "FLOAT" if dt == "FLOAT64" else ("INTEGER" if dt == "INT64" else ("BOOLEAN" if dt == "BOOL" else dt))
                col_meta[c] = {"type": norm_dt}

            # Fetch distinct categorical values for small STRING columns (<= 40 distinct)
            for sc in string_cols:
                if sc in ("notes", "primary_driver_note", "balance_sheet_driver_note", "cpcl_note", "what_happened_summary", "annual_report_context", "historical_10yr_context", "director_finance_action", "formula", "subtotal_formula", "description", "source_snippet", "verification_notes", "raw_label", "source_citation", "line_name_aliases", "ar_labels", "ten_year_label", "xbrl_tags"):
                    continue
                try:
                    q = f"""
                    SELECT `{sc}` AS v, COUNT(*) AS cnt
                    FROM `{PROJECT_ID}.{ds}.{tname}`
                    WHERE `{sc}` IS NOT NULL
                    GROUP BY 1
                    ORDER BY 2 DESC
                    LIMIT 45
                    """
                    vals = list(bq.query(q, job_config=bigquery.QueryJobConfig(labels=ATTRIBUTION_LABELS)).result())
                    if 0 < len(vals) <= 40:
                        col_meta[sc]["distinct"] = len(vals)
                        col_meta[sc]["values"] = [str(v.v) for v in vals]
                        col_meta[sc]["value_counts"] = {str(v.v): int(v.cnt) for v in vals}
                except Exception:
                    pass

            for bc in bool_cols:
                col_meta[bc]["values"] = ["true", "false"]

            # Min/max on first few numeric cols per table if helpful
            if num_cols and tname in (
                "ssot_corporate_annual_360",
                "ssot_refinery_economics_360",
                "fact_marketing_sales",
                "fact_pipeline_ops",
                "fact_wacc_annual",
                "fact_mou_scorecard",
                "subsidiary_financials",
            ):
                exprs = []
                for nc in num_cols[:25]:
                    exprs.append(f"MIN(`{nc}`) AS min__{nc}, MAX(`{nc}`) AS max__{nc}")
                try:
                    agg = list(
                        bq.query(
                            f"SELECT {', '.join(exprs)} FROM `{PROJECT_ID}.{ds}.{tname}`",
                            job_config=bigquery.QueryJobConfig(labels=ATTRIBUTION_LABELS),
                        ).result()
                    )[0]
                    for nc in num_cols[:25]:
                        mn = getattr(agg, f"min__{nc}", None)
                        mx = getattr(agg, f"max__{nc}", None)
                        if mn is not None:
                            col_meta[nc]["min"] = float(mn)
                        if mx is not None:
                            col_meta[nc]["max"] = float(mx)
                except Exception:
                    pass

            tables_out[full_key] = {"columns": col_meta}
            print(f"Profiled {full_key}: {len(col_meta)} cols", flush=True)

    return {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "project": PROJECT_ID,
        "tables": tables_out,
    }


def build_entities() -> Dict[str, Any]:
    return {
        "work_centres": {
            "WC-DEL": {"name": "IndianOil Bhavan, Corporate HQ New Delhi", "short_name": "Delhi Corporate HQ", "city": "New Delhi", "state": "Delhi", "sector": "HQ", "type": "office", "onshore_offshore": "onshore"},
            "WC-RHQ": {"name": "Refineries Division HQ, New Delhi", "short_name": "Refineries HQ", "city": "New Delhi", "state": "Delhi", "sector": "Refineries", "type": "office", "onshore_offshore": "onshore"},
            "WC-MUM": {"name": "IndianOil Bhavan, Marketing HQ Mumbai", "short_name": "Marketing HQ Mumbai", "city": "Mumbai", "state": "Maharashtra", "sector": "Marketing", "type": "office", "onshore_offshore": "onshore"},
            "WC-NOI": {"name": "Pipelines Division HQ, Noida", "short_name": "Pipelines HQ Noida", "city": "Noida", "state": "Uttar Pradesh", "sector": "Pipelines", "type": "office", "onshore_offshore": "onshore"},
            "WC-PNP": {"name": "Panipat Refinery & Petrochemical Complex", "short_name": "Panipat Refinery", "city": "Panipat", "state": "Haryana", "sector": "North", "type": "refinery", "onshore_offshore": "inland"},
            "WC-PRD": {"name": "Paradip Refinery", "short_name": "Paradip Refinery", "city": "Paradip", "state": "Odisha", "sector": "East", "type": "refinery", "onshore_offshore": "coastal"},
            "WC-KOY": {"name": "Gujarat (Koyali) Refinery", "short_name": "Koyali Refinery", "city": "Vadodara", "state": "Gujarat", "sector": "West", "type": "refinery", "onshore_offshore": "inland"},
            "WC-MTH": {"name": "Mathura Refinery", "short_name": "Mathura Refinery", "city": "Mathura", "state": "Uttar Pradesh", "sector": "North", "type": "refinery", "onshore_offshore": "inland"},
            "WC-HLD": {"name": "Haldia Refinery", "short_name": "Haldia Refinery", "city": "Haldia", "state": "West Bengal", "sector": "East", "type": "refinery", "onshore_offshore": "coastal"},
            "WC-BRN": {"name": "Barauni Refinery", "short_name": "Barauni Refinery", "city": "Begusarai", "state": "Bihar", "sector": "East", "type": "refinery", "onshore_offshore": "inland"},
            "WC-BGR": {"name": "Bongaigaon Refinery", "short_name": "Bongaigaon Refinery", "city": "Chirang", "state": "Assam", "sector": "NE", "type": "refinery", "onshore_offshore": "inland"},
            "WC-GUW": {"name": "Guwahati Refinery", "short_name": "Guwahati Refinery", "city": "Guwahati", "state": "Assam", "sector": "NE", "type": "refinery", "onshore_offshore": "inland"},
            "WC-DGB": {"name": "Digboi Refinery", "short_name": "Digboi Refinery", "city": "Digboi", "state": "Assam", "sector": "NE", "type": "refinery", "onshore_offshore": "inland"},
        },
        "refineries": {
            "REF-PNP": {"name": "Panipat Refinery & Petrochemical Complex", "short_name": "Panipat Refinery", "state": "Haryana", "region": "Northern", "capacity_mmtpa": 15.0, "type": "REFINERY", "coastal_or_inland": "inland"},
            "REF-PRD": {"name": "Paradip Refinery", "short_name": "Paradip Refinery", "state": "Odisha", "region": "Eastern", "capacity_mmtpa": 15.0, "type": "REFINERY", "coastal_or_inland": "coastal"},
            "REF-KOY": {"name": "Gujarat (Koyali) Refinery", "short_name": "Koyali Refinery", "state": "Gujarat", "region": "Western", "capacity_mmtpa": 13.7, "type": "REFINERY", "coastal_or_inland": "inland"},
            "REF-MTH": {"name": "Mathura Refinery", "short_name": "Mathura Refinery", "state": "Uttar Pradesh", "region": "Northern", "capacity_mmtpa": 8.0, "type": "REFINERY", "coastal_or_inland": "inland"},
            "REF-HLD": {"name": "Haldia Refinery", "short_name": "Haldia Refinery", "state": "West Bengal", "region": "Eastern", "capacity_mmtpa": 8.0, "type": "REFINERY", "coastal_or_inland": "coastal"},
            "REF-BRN": {"name": "Barauni Refinery", "short_name": "Barauni Refinery", "state": "Bihar", "region": "Eastern", "capacity_mmtpa": 6.0, "type": "REFINERY", "coastal_or_inland": "inland"},
            "REF-BGR": {"name": "Bongaigaon Refinery", "short_name": "Bongaigaon Refinery", "state": "Assam", "region": "North-East", "capacity_mmtpa": 2.7, "type": "REFINERY", "coastal_or_inland": "inland"},
            "REF-GUW": {"name": "Guwahati Refinery", "short_name": "Guwahati Refinery", "state": "Assam", "region": "North-East", "capacity_mmtpa": 1.2, "type": "REFINERY", "coastal_or_inland": "inland"},
            "REF-DGB": {"name": "Digboi Refinery", "short_name": "Digboi Refinery", "state": "Assam", "region": "North-East", "capacity_mmtpa": 0.65, "type": "REFINERY", "coastal_or_inland": "inland"},
            "DIV-MKT": {"name": "Marketing & Retail Division", "short_name": "Marketing Division", "state": "Maharashtra", "region": "All-India", "type": "MARKETING_DIVISION"},
            "DIV-PIP": {"name": "Cross-Country Pipelines Division", "short_name": "Pipelines Division", "state": "Uttar Pradesh", "region": "All-India", "type": "PIPELINE_DIVISION"},
            "DIV-CRP": {"name": "Corporate, Petchem Inter-Segment & Eliminations", "short_name": "Corporate & Petchem", "state": "Delhi", "region": "All-India", "type": "CORPORATE_ADJUSTMENT"},
        },
        "subsidiaries": {
            "CPCL": {"name": "Chennai Petroleum Corporation Limited", "short_name": "CPCL (Manali)", "holding_pct": 51.89, "capacity_mmtpa": 10.5},
            "LIOC": {"name": "Lanka IOC PLC", "short_name": "Lanka IOC", "holding_pct": 75.12},
            "IOCME": {"name": "IOC Middle East FZE", "short_name": "IOC Middle East", "holding_pct": 100.0},
            "INDOIL": {"name": "IndOil Global B.V. & Upstream Assets", "short_name": "IndOil Global", "holding_pct": 100.0},
            "JV_POOL": {"name": "Joint Ventures & Associates (HURL, Petronet LNG)", "short_name": "JV Pool", "holding_pct": 29.67},
            "CONSOL_ADJ": {"name": "Inter-Company & Consolidation Adjustments", "short_name": "Consolidation Adj.", "holding_pct": 100.0},
        },
        "products": {
            "MS": {"name": "Motor Spirit (Petrol / XP95 / XP100)", "short_name": "Petrol (MS)"},
            "HSD": {"name": "High Speed Diesel (HSD / XtraGreen)", "short_name": "Diesel (HSD)"},
            "ATF": {"name": "Aviation Turbine Fuel (ATF)", "short_name": "ATF"},
            "LPG": {"name": "Indane Liquefied Petroleum Gas (LPG)", "short_name": "Indane LPG"},
            "NAPHTHA_BITUMEN": {"name": "Naphtha, Bitumen, FO & Specialties", "short_name": "Bitumen & Naphtha"},
            "PETCHEM_LUBES": {"name": "Petrochemicals (Polymers/PX/PTA) & SERVO Lubes", "short_name": "Petchem & SERVO"},
            "EXPORTS": {"name": "Refined Product Exports & Bunkers", "short_name": "Exports"},
        },
        "pipelines": {
            "CRUDE_OIL": {"name": "Crude Oil Pipelines Network", "short_name": "Crude Pipelines"},
            "PRODUCT": {"name": "Petroleum Product Pipelines Network", "short_name": "Product Pipelines"},
            "GAS": {"name": "Natural Gas Pipelines Network", "short_name": "Gas Pipelines"},
        },
        "disciplines": {
            "DISC-FIN": {"code": "FIN", "function": "finance", "name": "Finance & Accounts (F&A)"},
            "DISC-TRS": {"code": "TRS", "function": "finance", "name": "Corporate Treasury, Crude & Forex"},
            "DISC-REF": {"code": "REF", "function": "refineries", "name": "Refineries & Process Operations"},
            "DISC-MKT": {"code": "MKT", "function": "marketing", "name": "Marketing & Retail Operations"},
            "DISC-PIP": {"code": "PIP", "function": "pipelines", "name": "Cross-Country Pipelines"},
            "DISC-PCH": {"code": "PCH", "function": "petchem", "name": "Petrochemicals & Specialty Lubes"},
            "DISC-BD": {"code": "BD", "function": "strategy", "name": "Business Development & Net-Zero 2046"},
        },
        "fields": {},
        "grades": {
            "A": {"name": "Grade A · Officer / Accounts Officer", "level_order": 1, "cadre": "executive", "compat_e": "E1"},
            "B": {"name": "Grade B · Finance Officer / Engineer", "level_order": 2, "cadre": "executive", "compat_e": "E2"},
            "C": {"name": "Grade C · Manager (Finance / Operations)", "level_order": 3, "cadre": "executive", "compat_e": "E3"},
            "D": {"name": "Grade D · Senior Manager", "level_order": 4, "cadre": "executive", "compat_e": "E4"},
            "E": {"name": "Grade E · Chief Manager", "level_order": 5, "cadre": "executive", "compat_e": "E5"},
            "F": {"name": "Grade F · Deputy General Manager (DGM)", "level_order": 6, "cadre": "executive", "compat_e": "E6"},
            "G": {"name": "Grade G · General Manager (GM)", "level_order": 7, "cadre": "executive", "compat_e": "E7"},
            "H": {"name": "Grade H · Chief General Manager (CGM)", "level_order": 8, "cadre": "executive", "compat_e": "E8"},
            "I": {"name": "Grade I · Executive Director (ED)", "level_order": 9, "cadre": "executive", "compat_e": "E9"},
        },
    }


def build_aliases() -> Dict[str, Any]:
    return {
        "version": 1,
        "work_centres": {
            "WC-DEL": ["delhi", "new delhi", "corporate hq", "indianoil bhavan delhi", "scope complex", "दिल्ली", "नई दिल्ली"],
            "WC-RHQ": ["refineries hq", "refinery hq", "scope complex refineries"],
            "WC-MUM": ["mumbai", "marketing hq", "indianoil bhavan mumbai", "bandra kurla", "bkc", "मुंबई"],
            "WC-NOI": ["noida", "pipelines hq", "pipeline hq"],
            "WC-PNP": ["panipat", "panipat refinery", "p-25", "पानीपत"],
            "WC-PRD": ["paradip", "paradip refinery", "पारादीप"],
            "WC-KOY": ["koyali", "gujarat refinery", "vadodara refinery", "baroda", "कोयली", "गुजरात रिफाइनरी"],
            "WC-MTH": ["mathura", "mathura refinery", "मथुरा"],
            "WC-HLD": ["haldia", "haldia refinery", "हल्दिया"],
            "WC-BRN": ["barauni", "barauni refinery", "बरौनी"],
            "WC-BGR": ["bongaigaon", "bongaigaon refinery", "बोंगाईगांव"],
            "WC-GUW": ["guwahati", "guwahati refinery", "noonmati", "गुवाहाटी"],
            "WC-DGB": ["digboi", "digboi refinery", "डिगबोई"],
        },
        "work_centre_notes": {
            "WC-PNP": "15.0 MMTPA expanding to 25.0 MMTPA (P-25) + Naphtha Cracker & PX/PTA",
            "WC-PRD": "15.0 MMTPA complex coastal refinery with highest GRM complexity",
        },
        "regions": {
            "north east": {"sector": "NE"},
            "north-east": {"sector": "NE"},
            "northeast": {"sector": "NE"},
            "coastal refineries": {"wc_ids": ["WC-PRD", "WC-HLD"]},
            "inland refineries": {"wc_ids": ["WC-PNP", "WC-KOY", "WC-MTH", "WC-BRN", "WC-BGR", "WC-GUW", "WC-DGB"]},
            "north east refineries": {"wc_ids": ["WC-BGR", "WC-GUW", "WC-DGB"]},
            "corporate offices": {"type": "office"},
        },
        "refineries": {
            "REF-PNP": ["panipat", "panipat refinery", "pnp", "p-25"],
            "REF-PRD": ["paradip", "paradip refinery", "prd"],
            "REF-KOY": ["koyali", "gujarat refinery", "koyali refinery", "vadodara"],
            "REF-MTH": ["mathura", "mathura refinery", "mth"],
            "REF-HLD": ["haldia", "haldia refinery", "hld"],
            "REF-BRN": ["barauni", "barauni refinery", "brn"],
            "REF-BGR": ["bongaigaon", "bongaigaon refinery", "bgr"],
            "REF-GUW": ["guwahati", "guwahati refinery", "guw", "noonmati"],
            "REF-DGB": ["digboi", "digboi refinery", "dgb"],
            "DIV-MKT": ["marketing division", "marketing reconciliation"],
            "DIV-PIP": ["pipelines division", "pipeline reconciliation"],
            "DIV-CRP": ["corporate division", "corporate reconciliation"],
        },
        "subsidiaries": {
            "CPCL": ["cpcl", "chennai petroleum", "manali refinery"],
            "LIOC": ["lanka ioc", "lioc", "sri lanka"],
            "IOCME": ["ioc middle east", "iocme", "dubai"],
            "INDOIL": ["indoil", "indoil global"],
            "JV_POOL": ["hurl", "petronet", "petronet lng", "joint ventures"],
            "CONSOL_ADJ": ["consolidation adjustment", "eliminations"],
        },
        "products": {
            "MS": ["ms", "petrol", "motor spirit", "xp95", "xp100"],
            "HSD": ["hsd", "diesel", "high speed diesel", "xtragreen"],
            "ATF": ["atf", "aviation turbine fuel", "jet fuel"],
            "LPG": ["lpg", "indane", "indane lpg", "cooking gas"],
            "NAPHTHA_BITUMEN": ["bitumen", "naphtha", "furnace oil"],
            "PETCHEM_LUBES": ["petrochemicals", "petchem", "servo", "lubes", "lubricants", "polymers"],
            "EXPORTS": ["exports", "bunkers"],
        },
        "pipelines": {
            "CRUDE_OIL": ["crude oil pipeline", "crude pipeline", "salaya mathura", "phbpl"],
            "PRODUCT": ["product pipeline", "petroleum product pipeline", "paradip hyderabad"],
            "GAS": ["gas pipeline", "natural gas pipeline", "dadri panipat"],
        },
        "disciplines": {
            "DISC-FIN": ["finance", "f&a", "finance and accounts", "accounts", "pricing & excise", "वित्त"],
            "DISC-TRS": ["treasury", "forex", "fx", "hedging", "crude import"],
            "DISC-REF": ["refineries", "refining", "process"],
            "DISC-MKT": ["marketing", "retail", "indane", "servo"],
            "DISC-PIP": ["pipelines", "pipeline operations"],
            "DISC-PCH": ["petrochemicals", "petchem", "polymers"],
            "DISC-BD": ["business development", "net zero", "green hydrogen"],
        },
        "discipline_groups": {
            "finance": ["DISC-FIN", "DISC-TRS"],
            "downstream": ["DISC-REF", "DISC-MKT", "DISC-PIP", "DISC-PCH"],
        },
        "fields": {},
        "grades": {
            "A": ["grade a", "accounts officer", "e1"],
            "B": ["grade b", "finance officer", "e2"],
            "C": ["grade c", "manager finance", "e3"],
            "D": ["grade d", "sr manager", "senior manager", "e4"],
            "E": ["grade e", "chief manager", "e5"],
            "F": ["grade f", "dgm", "deputy general manager", "e6"],
            "G": ["grade g", "gm", "general manager", "e7"],
            "H": ["grade h", "cgm", "chief general manager", "e8"],
            "I": ["grade i", "ed", "executive director", "e9"],
        },
    }


def main() -> None:
    bq = bigquery.Client(project=PROJECT_ID, location=BQ_LOCATION)
    cat = build_catalog(bq)
    (SEM_DIR / "semantic_catalog.json").write_text(json.dumps(cat, indent=2), encoding="utf-8")
    print(f"Wrote {SEM_DIR / 'semantic_catalog.json'} ({len(cat['tables'])} tables)", flush=True)

    ents = build_entities()
    (SEM_DIR / "entities.json").write_text(json.dumps(ents, indent=2), encoding="utf-8")
    print(f"Wrote {SEM_DIR / 'entities.json'}", flush=True)

    aliases = build_aliases()
    (SEM_DIR / "entity_aliases.yaml").write_text(yaml.safe_dump(aliases, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"Wrote {SEM_DIR / 'entity_aliases.yaml'}", flush=True)


if __name__ == "__main__":
    main()
