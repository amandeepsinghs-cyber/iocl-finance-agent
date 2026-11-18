#!/usr/bin/env python3
"""
Step 4 Verification Gate: Verify >= 200 IOCL FY17-FY26 Accounting, Cross-Statement,
Parquet-vs-JSON, Waterfall Bridge, and Downstream 360 Sum-Reconciliation Identities.

Fails (exit code 1) if ANY check has error > tolerance (0.00 Cr for internal identities).
Writes `financial_ssot/out/recon_checks.parquet` and `financial_build/data/recon_checks.json`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "yukti" / "backend"))

from app.brain.bridge import BridgeOk, bridge  # noqa: E402

DATA_DIR = REPO_ROOT / "financial_build" / "data"
SSOT_OUT = REPO_ROOT / "financial_ssot" / "out"
FYS = [f"FY{y}" for y in range(17, 27)]

EXPECTED_ANCHORS = {
    "FY17": {"gross": 445441.90, "excise": 85499.75, "net": 359942.15, "pat": 19106.40, "nw": 99728.72, "debt": 50384.80, "tp": 65.19, "grm": 10.22},
    "FY18": {"gross": 506427.59, "excise": 82388.89, "net": 424038.70, "pat": 21346.12, "nw": 110171.02, "debt": 55525.63, "tp": 69.00, "grm": 8.49},
    "FY19": {"gross": 605932.34, "excise": 78231.08, "net": 527701.26, "pat": 16894.15, "nw": 108657.51, "debt": 83259.91, "tp": 71.92, "grm": 5.41},
    "FY20": {"gross": 566353.55, "excise": 80693.19, "net": 485660.36, "pat": 1313.23, "nw": 93768.87, "debt": 112736.72, "tp": 69.41, "grm": 0.08},
    "FY21": {"gross": 514890.47, "excise": 136832.86, "net": 378057.61, "pat": 21836.04, "nw": 110500.04, "debt": 94413.00, "tp": 62.35, "grm": 5.64},
    "FY22": {"gross": 728445.40, "excise": 130296.19, "net": 598149.21, "pat": 24184.10, "nw": 131286.36, "debt": 110798.50, "tp": 67.67, "grm": 11.25},
    "FY23": {"gross": 934952.66, "excise": 95480.46, "net": 839472.20, "pat": 8241.82, "nw": 134757.54, "debt": 132495.45, "tp": 72.41, "grm": 19.52},
    "FY24": {"gross": 866345.38, "excise": 91996.79, "net": 774348.59, "pat": 39618.84, "nw": 176714.98, "debt": 116495.74, "tp": 73.59, "grm": 12.05},
    "FY25": {"gross": 845512.61, "excise": 89562.99, "net": 755949.62, "pat": 12961.57, "nw": 178676.86, "debt": 134465.54, "tp": 71.56, "grm": 4.80},
    "FY26": {"gross": 886224.41, "excise": 102066.54, "net": 784157.87, "pat": 36802.42, "nw": 204544.34, "debt": 110668.22, "tp": 75.451, "grm": 10.85},
}


def main() -> None:
    cw_rows = json.loads((DATA_DIR / "iocl_10yr_corporate_wide.json").read_text())
    pnl_rows = json.loads((DATA_DIR / "iocl_10yr_schedule_iii_lines.json").read_text())
    bs_rows = json.loads((DATA_DIR / "iocl_10yr_balance_sheet_lines.json").read_text())
    cf_rows = json.loads((DATA_DIR / "iocl_10yr_cash_flow_lines.json").read_text())
    ratio_rows = json.loads((DATA_DIR / "iocl_10yr_ratios_lines.json").read_text())
    ref_rows = json.loads((DATA_DIR / "ssot_refinery_economics_360.json").read_text())
    mkt_rows = json.loads((DATA_DIR / "fact_marketing_sales.json").read_text())
    pip_rows = json.loads((DATA_DIR / "fact_pipeline_ops.json").read_text())
    seg_rows = json.loads((DATA_DIR / "fact_segment.json").read_text())
    sub_rows = json.loads((DATA_DIR / "subsidiary_financials.json").read_text())
    mou_rows = json.loads((DATA_DIR / "fact_mou_scorecard.json").read_text())
    fact_df = pq.read_table(SSOT_OUT / "fact_snapshot.parquet").to_pandas()

    checks: List[Dict[str, Any]] = []

    def record(check_id: str, domain: str, fy: str, expected: float, actual: float, tol: float = 0.001, severity: str = "BLOCK") -> None:
        delta = round(abs(float(expected) - float(actual)), 6)
        status = "PASS" if delta <= tol else "FAIL"
        checks.append({
            "run_id": "20261116T000000Z",
            "check_id": check_id,
            "domain": domain,
            "fiscal_year": fy,
            "severity": severity,
            "expected_value": float(expected),
            "actual_value": float(actual),
            "abs_delta": delta,
            "tolerance": tol,
            "status": status,
        })

    def idx_map(rows: List[Dict[str, Any]], val_col: str = "amount_inr_cr") -> Dict[tuple[str, str], float]:
        return {(r["fiscal_year"], r["line_code"]): float(r[val_col]) for r in rows}

    pnl_m = idx_map(pnl_rows)
    bs_m = idx_map(bs_rows)
    cf_m = idx_map(cf_rows)
    rat_m = idx_map(ratio_rows, "value")
    cw_by_fy = {r["fiscal_year"]: r for r in cw_rows}

    # Global cardinality & uniqueness checks
    assert len(cw_rows) == 10
    assert len(pnl_rows) == 250
    assert len(bs_rows) == 270
    assert len(cf_rows) == 180
    assert len(ratio_rows) == 180
    assert len(ref_rows) == 120
    assert len(mkt_rows) == 70
    assert len(pip_rows) == 30
    assert len(sub_rows) == 60
    assert len(mou_rows) == 24

    dups_latest = fact_df[fact_df["is_latest_vintage"] == True].duplicated(subset=["fiscal_year", "scope", "period_type", "line_code"]).sum()  # noqa: E712
    dups_own = fact_df[fact_df["is_own_vintage"] == True].duplicated(subset=["fiscal_year", "scope", "period_type", "line_code"]).sum()  # noqa: E712
    record("SSOT-UNIQ-LATEST", "parquet_integrity", "ALL", 0.0, float(dups_latest))
    record("SSOT-UNIQ-OWN", "parquet_integrity", "ALL", 0.0, float(dups_own))

    # Special FY anchors (100% verbatim AR figures)
    record("ANC-FY20-CORE-GRM", "anchor", "FY20", 4.10, cw_by_fy["FY20"]["core_grm_usd_bbl"])
    record("ANC-FY20-EXC", "anchor", "FY20", -11304.64, cw_by_fy["FY20"]["exceptional_items_inr_cr"])
    record("ANC-FY22-EXCH", "anchor", "FY22", 264436.00, cw_by_fy["FY22"]["exchequer_contribution_inr_cr"])
    record("ANC-FY23-EXCH", "anchor", "FY23", 240185.00, cw_by_fy["FY23"]["exchequer_contribution_inr_cr"])
    record("ANC-FY24-EXCH", "anchor", "FY24", 232299.00, cw_by_fy["FY24"]["exchequer_contribution_inr_cr"])
    record("ANC-FY26-CONSOL-PAT", "anchor", "FY26", 43677.32, cw_by_fy["FY26"]["consolidated_pat_inr_cr"])
    record("ANC-FY26-PIP-MMT", "anchor", "FY26", 105.556, cw_by_fy["FY26"]["pipeline_throughput_mmt"])
    record("ANC-FY26-MKT-MMT", "anchor", "FY26", 105.117, cw_by_fy["FY26"]["marketing_sales_mmt"])
    record("ANC-FY26-UTIL", "anchor", "FY26", 107.4, cw_by_fy["FY26"]["refining_capacity_utilization_pct"], tol=0.1)
    record("ANC-FY26-DE", "anchor", "FY26", 0.54, cw_by_fy["FY26"]["debt_to_equity_ratio"])
    record("ANC-FY26-EPS", "anchor", "FY26", 26.72, cw_by_fy["FY26"]["eps_basic_inr"])
    record("ANC-FY26-BVPS", "anchor", "FY26", 148.53, cw_by_fy["FY26"]["book_value_per_share_inr"])

    for fy in FYS:
        a = EXPECTED_ANCHORS[fy]
        cw = cw_by_fy[fy]
        record(f"DIV-{fy}-PAYOUT", "cash_flow", fy, abs(cw["dividend_paid_cf_inr_cr"]), cw["total_dividend_payout_inr_cr"])

        # 1. Exact published anchors (8 checks/FY)
        record(f"ANC-{fy}-GROSS", "anchor", fy, a["gross"], pnl_m[(fy, "gross_revenue_inr_cr")])
        record(f"ANC-{fy}-EXCISE", "anchor", fy, a["excise"], pnl_m[(fy, "statutory_levies_total_inr_cr")])
        record(f"ANC-{fy}-NET", "anchor", fy, a["net"], pnl_m[(fy, "net_revenue_inr_cr")])
        record(f"ANC-{fy}-PAT", "anchor", fy, a["pat"], pnl_m[(fy, "pat_inr_cr")])
        record(f"ANC-{fy}-NW", "anchor", fy, a["nw"], bs_m[(fy, "net_worth_inr_cr")])
        record(f"ANC-{fy}-DEBT", "anchor", fy, a["debt"], cw["total_debt_inr_cr"])
        record(f"ANC-{fy}-REFTP", "anchor", fy, a["tp"], cw["refining_throughput_mmt"])
        record(f"ANC-{fy}-GRM", "anchor", fy, a["grm"], rat_m[(fy, "gross_refining_margin_usd_bbl")])

        # 2. Schedule III P&L identities (7 checks/FY)
        record(f"PL-{fy}-SEG-REV", "pnl", fy, pnl_m[(fy, "gross_revenue_inr_cr")], pnl_m[(fy, "petroleum_products_revenue_inr_cr")] + pnl_m[(fy, "petchem_and_other_op_rev_inr_cr")])
        record(f"PL-{fy}-TOTINC", "pnl", fy, pnl_m[(fy, "total_income_inr_cr")], pnl_m[(fy, "gross_revenue_inr_cr")] + pnl_m[(fy, "other_income_inr_cr")])
        record(f"PL-{fy}-NETREV", "pnl", fy, pnl_m[(fy, "net_revenue_inr_cr")], pnl_m[(fy, "gross_revenue_inr_cr")] - pnl_m[(fy, "statutory_levies_total_inr_cr")])
        tot_exp = sum(pnl_m[(fy, c)] for c in [
            "statutory_levies_total_inr_cr", "cost_of_materials_consumed_inr_cr",
            "purchases_stock_in_trade_inr_cr", "inventory_change_inr_cr",
            "employee_benefit_net_pnl_inr_cr", "impairment_fin_assets_inr_cr",
            "other_expenses_inr_cr", "dda_inr_cr", "finance_costs_inr_cr",
        ])
        record(f"PL-{fy}-TOTEXP", "pnl", fy, pnl_m[(fy, "total_expenses_inr_cr")], tot_exp)
        record(f"PL-{fy}-PBTPRE", "pnl", fy, pnl_m[(fy, "pbt_pre_exc_inr_cr")], pnl_m[(fy, "total_income_inr_cr")] - pnl_m[(fy, "total_expenses_inr_cr")])
        record(f"PL-{fy}-PBT", "pnl", fy, pnl_m[(fy, "pbt_inr_cr")], pnl_m[(fy, "pbt_pre_exc_inr_cr")] + pnl_m[(fy, "exceptional_items_inr_cr")])
        record(f"PL-{fy}-PAT", "pnl", fy, pnl_m[(fy, "pat_inr_cr")], pnl_m[(fy, "pbt_inr_cr")] - pnl_m[(fy, "tax_expense_total_inr_cr")])
        record(f"PL-{fy}-TAXSUM", "pnl", fy, pnl_m[(fy, "tax_expense_total_inr_cr")], pnl_m[(fy, "current_tax_inr_cr")] + pnl_m[(fy, "deferred_tax_inr_cr")])

        # 3. Balance Sheet identities (7 checks/FY)
        nca_sum = sum(bs_m[(fy, c)] for c in ["refinery_petchem_ppe_inr_cr", "cwip_inr_cr", "investments_subsidiaries_jv_inr_cr", "other_non_current_assets_inr_cr"])
        ca_sum = sum(bs_m[(fy, c)] for c in ["inventories_inr_cr", "current_investments_inr_cr", "receivables_outstanding_inr_cr", "cash_and_bank_inr_cr", "other_bank_balances_inr_cr", "other_current_assets_inr_cr"])
        record(f"BS-{fy}-NCA", "balance_sheet", fy, bs_m[(fy, "non_current_assets_inr_cr")], nca_sum)
        record(f"BS-{fy}-CA", "balance_sheet", fy, bs_m[(fy, "current_assets_inr_cr")], ca_sum)
        record(f"BS-{fy}-TA", "balance_sheet", fy, bs_m[(fy, "total_assets_inr_cr")], bs_m[(fy, "non_current_assets_inr_cr")] + bs_m[(fy, "current_assets_inr_cr")])
        record(f"BS-{fy}-EQ", "balance_sheet", fy, bs_m[(fy, "net_worth_inr_cr")], bs_m[(fy, "equity_share_capital_inr_cr")] + bs_m[(fy, "other_equity_reserves_inr_cr")])
        record(f"BS-{fy}-DEBT", "balance_sheet", fy, cw["total_debt_inr_cr"], bs_m[(fy, "long_term_debt_inr_cr")] + bs_m[(fy, "short_term_debt_inr_cr")])
        ncl_sum = sum(bs_m[(fy, c)] for c in ["long_term_debt_inr_cr", "lease_liabilities_non_current_inr_cr", "deferred_tax_liability_net_inr_cr", "other_non_current_liabilities_inr_cr"])
        cl_sum = sum(bs_m[(fy, c)] for c in ["short_term_debt_inr_cr", "lease_liabilities_current_inr_cr", "trade_payables_inr_cr", "other_current_liabilities_inr_cr"])
        record(f"BS-{fy}-NCL", "balance_sheet", fy, bs_m[(fy, "non_current_liabilities_inr_cr")], ncl_sum)
        record(f"BS-{fy}-CL", "balance_sheet", fy, bs_m[(fy, "current_liabilities_inr_cr")], cl_sum)
        record(f"BS-{fy}-EQ-LIAB", "balance_sheet", fy, bs_m[(fy, "total_assets_inr_cr")], bs_m[(fy, "net_worth_inr_cr")] + bs_m[(fy, "non_current_liabilities_inr_cr")] + bs_m[(fy, "current_liabilities_inr_cr")])

        # 4. Cash Flow & BS Tie-Out (7 checks/FY)
        record(f"CF-{fy}-CFO", "cash_flow", fy, cf_m[(fy, "operating_cash_flow_inr_cr")], sum(cf_m[(fy, c)] for c in ["pbt_inr_cr", "non_cash_adjustments_cf_inr_cr", "working_capital_change_cf_inr_cr", "income_tax_paid_cf_inr_cr"]))
        record(f"CF-{fy}-CFI", "cash_flow", fy, cf_m[(fy, "investing_cash_flow_inr_cr")], sum(cf_m[(fy, c)] for c in ["capex_cash_outflow_inr_cr", "subsidiary_investment_cf_inr_cr", "dividend_interest_received_cf_inr_cr"]))
        record(f"CF-{fy}-CFF", "cash_flow", fy, cf_m[(fy, "financing_cash_flow_inr_cr")], sum(cf_m[(fy, c)] for c in ["net_borrowings_cf_inr_cr", "lease_payments_cf_inr_cr", "interest_paid_cf_inr_cr", "dividend_paid_cf_inr_cr"]))
        record(f"CF-{fy}-NETCHG", "cash_flow", fy, cf_m[(fy, "net_cash_change_inr_cr")], cf_m[(fy, "operating_cash_flow_inr_cr")] + cf_m[(fy, "investing_cash_flow_inr_cr")] + cf_m[(fy, "financing_cash_flow_inr_cr")])
        record(f"CF-{fy}-CLOSE", "cash_flow", fy, cf_m[(fy, "closing_cash_inr_cr")], cf_m[(fy, "opening_cash_inr_cr")] + cf_m[(fy, "net_cash_change_inr_cr")])
        record(f"CF-{fy}-BSTIE", "cash_flow", fy, bs_m[(fy, "cash_and_bank_inr_cr")], cf_m[(fy, "closing_cash_inr_cr")])
        record(f"CF-{fy}-FCF", "cash_flow", fy, cf_m[(fy, "free_cash_flow_inr_cr")], cf_m[(fy, "operating_cash_flow_inr_cr")] + cf_m[(fy, "capex_cash_outflow_inr_cr")])
        if fy != "FY17":
            prev_fy = f"FY{int(fy[2:]) - 1:02d}"
            record(f"CF-{fy}-OPEN-TIE", "cash_flow", fy, cf_m[(prev_fy, "closing_cash_inr_cr")], cf_m[(fy, "opening_cash_inr_cr")])

        # 5. Python Waterfall Bridge Parity (2 checks/FY)
        fy_pnl_rows = [r for r in pnl_rows if r["fiscal_year"] == fy]
        for gran in ("standard", "full"):
            res = bridge(fy_pnl_rows, period=fy, granularity=gran)
            ok = isinstance(res, BridgeOk)
            end_v = res.end_value if ok else -999999.0
            record(f"BRG-{fy}-{gran.upper()}", "bridge", fy, pnl_m[(fy, "pat_inr_cr")], end_v, tol=0.01)
            if gran == "standard" and ok:
                in_bounds = 10 <= len(res.bars) <= 15 and not any("ebitda" in b.label.lower() for b in res.bars)
                record(f"BRG-{fy}-BARS", "bridge", fy, 1.0, 1.0 if in_bounds else 0.0)

        # 6. Downstream 360 Sum Reconciliation (11 checks/FY)
        fy_ref_all = [r for r in ref_rows if r["fiscal_year"] == fy]
        fy_ref_only = [r for r in fy_ref_all if r["unit_type"] == "REFINERY"]
        assert len(fy_ref_only) == 9
        record(f"REF-{fy}-CAP", "refinery_360", fy, 70.25, sum(r["installed_capacity_mmtpa"] for r in fy_ref_only))
        tp_sum = sum(r["throughput_mmt"] for r in fy_ref_only)
        record(f"REF-{fy}-TP", "refinery_360", fy, cw["refining_throughput_mmt"], tp_sum)
        w_grm = sum(r["throughput_mmt"] * r["grm_usd_bbl"] for r in fy_ref_only) / tp_sum
        record(f"REF-{fy}-GRM", "refinery_360", fy, cw["gross_refining_margin_usd_bbl"], round(w_grm, 2), tol=0.01)
        for col in ["gross_revenue_inr_cr", "excise_duty_inr_cr", "net_revenue_inr_cr", "ebitda_inr_cr", "dda_inr_cr", "finance_costs_inr_cr", "pbt_inr_cr"]:
            record(f"REF-{fy}-SUM-{col[:6].upper()}", "refinery_360", fy, cw[col], sum(r[col] for r in fy_ref_all))

        fy_mkt = [r for r in mkt_rows if r["fiscal_year"] == fy]
        record(f"MKT-{fy}-VOL", "marketing_360", fy, cw["marketing_sales_mmt"], sum(r["sales_volume_mmt"] for r in fy_mkt))

        fy_pip = [r for r in pip_rows if r["fiscal_year"] == fy]
        record(f"PIP-{fy}-TP", "pipeline_360", fy, cw["pipeline_throughput_mmt"], sum(r["throughput_mmt"] for r in fy_pip))

        fy_seg_rev = sum(r["value_inr_cr"] for r in seg_rows if r["fiscal_year"] == fy and r["metric"] == "segment_revenue")
        fy_seg_ebit = sum(r["value_inr_cr"] for r in seg_rows if r["fiscal_year"] == fy and r["metric"] == "segment_result_ebit")
        record(f"SEG-{fy}-REV", "segment_360", fy, cw["gross_revenue_inr_cr"], fy_seg_rev)
        record(f"SEG-{fy}-PBT", "segment_360", fy, cw["pbt_inr_cr"], fy_seg_ebit - cw["finance_costs_inr_cr"])

        fy_sub = [r for r in sub_rows if r["fiscal_year"] == fy]
        record(f"SUB-{fy}-CONSOL-PAT", "subsidiaries", fy, cw["consolidated_pat_inr_cr"], cw["pat_inr_cr"] + sum(r["iocl_share_pat_inr_cr"] for r in fy_sub))
        record(f"SUB-{fy}-CONSOL-REV", "subsidiaries", fy, cw["consolidated_revenue_inr_cr"], cw["gross_revenue_inr_cr"] + sum(r["revenue_inr_cr"] for r in fy_sub))

        # 7. Parquet fact_snapshot vs JSON Parity (7 checks/FY)
        sub_pq = fact_df[(fact_df["fiscal_year"] == fy) & (fact_df["scope"] == "standalone") & (fact_df["is_latest_vintage"] == True)]  # noqa: E712
        pq_map = {r["line_code"]: (r["value_inr_cr"] if pd.notna(r["value_inr_cr"]) else r["value"]) for _, r in sub_pq.iterrows()}
        for lc, cw_k in [
            ("PL.REV_OPS", "gross_revenue_inr_cr"), ("PL.STAT_LEVIES", "excise_duty_inr_cr"),
            ("PL.PAT", "pat_inr_cr"), ("BS.TOTAL_ASSETS", "total_assets_inr_cr"),
            ("BS.EQUITY.TOTAL", "net_worth_inr_cr"), ("BS.BORROW_TOTAL_10YR", "total_debt_inr_cr"),
            ("CF.CFO", "operating_cash_flow_inr_cr"), ("CF.CCE_CLOSE", "closing_cash_inr_cr"),
        ]:
            record(f"PQ-{fy}-{lc}", "parquet_parity", fy, cw[cw_k], pq_map[lc])

    recon_df = pd.DataFrame(checks)
    recon_df.to_parquet(SSOT_OUT / "recon_checks.parquet", index=False)
    (DATA_DIR / "recon_checks.json").write_text(json.dumps(checks, indent=2) + "\n", encoding="utf-8")

    total = len(checks)
    failed = [c for c in checks if c["status"] != "PASS"]
    max_delta = max(c["abs_delta"] for c in checks)
    print(f"IOCL Verification Gate: {total} checks executed | {total - len(failed)} PASS | {len(failed)} FAIL | max_abs_delta={max_delta:.6f}")
    if failed:
        for f in failed[:15]:
            print("  FAIL:", f)
        sys.exit(1)
    assert total >= 200, f"Expected >= 200 checks, ran {total}"


if __name__ == "__main__":
    main()
