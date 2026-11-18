from pydantic import BaseModel, ConfigDict
from typing import Dict, Any, List

class AssumptionField(BaseModel):
    value: float
    source: str
    edited_by_user: bool = False

class DCFAssumptions(BaseModel):
    # Core editable
    wacc_pct: AssumptionField
    terminal_g_pct: AssumptionField
    brent_usd: AssumptionField
    capex_scale_pct: AssumptionField
    production_decline_pct: AssumptionField
    holdco_discount_pct: AssumptionField
    exit_ev_ebitda: AssumptionField
    
    # Internal variables passed along
    as_of: str
    run_id: str
    
    # Bridge components
    shares_outstanding: AssumptionField
    listed_investments_inr_cr: AssumptionField
    unlisted_investments_inr_cr: AssumptionField
    cash_and_equivalents_inr_cr: AssumptionField
    srf_deposits_inr_cr: AssumptionField
    decom_provision_inr_cr: AssumptionField
    borrowings_inr_cr: AssumptionField
    lease_liab_inr_cr: AssumptionField
    
    # Base numbers for forecast
    vol_crude_mmt: AssumptionField
    vol_gas_bcm: AssumptionField
    bbl_per_tonne: AssumptionField
    gcv_mmbtu_per_scm: AssumptionField
    fx_inr_usd: AssumptionField
    crude_realisation_discount_pct: AssumptionField
    gas_price_usd_mmbtu: AssumptionField
    vap_revenue_ratio: AssumptionField
    effective_levy_rate: AssumptionField
    opex_per_boe: AssumptionField
    inflation_pct: AssumptionField
    exploration_writeoff_ratio: AssumptionField
    dd_a_ratio: AssumptionField
    tax_rate_pct: AssumptionField
    capex_base_inr_cr: AssumptionField
    nwc_pct: AssumptionField
    market_price_inr: AssumptionField

    # IOCL Downstream optional drivers (keep None for generic upstream fixture tests)
    grm_usd_bbl: float = 0.0
    refining_throughput_mmt: float = 0.0
    marketing_sales_mmt: float = 0.0
    base_fcff_inr_cr: float = 0.0

    # Forecast overrides (for fixture testing)
    forecast_fcff: List[float] = []

    model_config = ConfigDict(frozen=True)

def _get_val(snapshot: List[Dict[str, Any]], code: str, default: float = 0.0) -> float:
    import math
    for row in snapshot:
        if row.get("line_code") == code and row.get("verified", False):
            for col in ("value_inr_cr", "value", "value_native"):
                raw = row.get(col)
                if raw is not None:
                    try:
                        f = float(raw)
                        if not math.isnan(f):
                            return f
                    except (TypeError, ValueError):
                        pass
    return default

def defaults_from_ssot(snapshot: List[Dict[str, Any]], wacc_table: List[Dict[str, Any]], as_of: str) -> DCFAssumptions:
    from app.finance.dcf.inputs import load_fy26_market_price_default, load_fy26_wacc_default

    def mk(val, src):
        return AssumptionField(value=float(val), source=src)

    # Find WACC from wacc_table or canonical fact_wacc_annual FY26 SSOT
    wacc_val, wacc_source, _ = load_fy26_wacc_default(wacc_table)
    for row in wacc_table:
        if row.get("fiscal_year") == "FY26" and row.get("verified", False):
            if row.get("wacc_pct") is not None:
                wacc_val = float(row["wacc_pct"])
                wacc_source = "fact_wacc_annual FY26"

    mkt_px, mkt_src, _ = load_fy26_market_price_default()

    # Filter snapshot
    valid_snapshot = []
    for row in snapshot:
        if row.get("verified", False):
            valid_snapshot.append(row)
            
    # Bridge variables
    cce = _get_val(valid_snapshot, "BS.CCE") + _get_val(valid_snapshot, "BS.OTHER_BANK_BAL")
    
    # fallback to INV.LISTED / INV.UNLISTED if unit test passes it
    inv_listed = _get_val(valid_snapshot, "BS.INVESTMENTS_NC")
    if inv_listed == 0.0: inv_listed = _get_val(valid_snapshot, "INV.LISTED")
    
    inv_unlisted = _get_val(valid_snapshot, "BS.INVESTMENTS_C")
    if inv_unlisted == 0.0: inv_unlisted = _get_val(valid_snapshot, "INV.UNLISTED")
    
    srf = _get_val(valid_snapshot, "BS.SRF_DEPOSIT_NC")
    if srf == 0.0: srf = _get_val(valid_snapshot, "BS.SRF_DEPOSIT")
    
    decom = _get_val(valid_snapshot, "NPROV.DECOM_CLOSE")
    if decom == 0.0: decom = _get_val(valid_snapshot, "PROV.DECOM")
    
    borrowings = _get_val(valid_snapshot, "BS.BORROW_NC") + _get_val(valid_snapshot, "BS.BORROW_CUR")
    if borrowings == 0.0: borrowings = _get_val(valid_snapshot, "BS.BORROWINGS.TOTAL")
    
    lease = _get_val(valid_snapshot, "BS.LEASE_LIAB_NC") + _get_val(valid_snapshot, "BS.LEASE_LIAB_C")
    if lease == 0.0: lease = _get_val(valid_snapshot, "BS.LEASE_LIAB.TOTAL")

    shares_cr = 1412.1238
    base_fcf = _get_val(valid_snapshot, "CF.CFO") - abs(_get_val(valid_snapshot, "CAPEX.TOTAL"))
    if base_fcf <= 0:
        base_fcf = 32270.0
    throughput = _get_val(valid_snapshot, "REF.THROUGHPUT_MMT")
    if throughput <= 0:
        throughput = 75.451
    grm = _get_val(valid_snapshot, "REF.GRM_USD_BBL")
    if grm <= 0:
        grm = 10.85
    mkt_vol = _get_val(valid_snapshot, "MKT.SALES_MMT")
    if mkt_vol <= 0:
        mkt_vol = 105.117
    capex_base = abs(_get_val(valid_snapshot, "CAPEX.TOTAL"))
    if capex_base <= 0:
        capex_base = 34210.0

    return DCFAssumptions(
        wacc_pct=mk(wacc_val, wacc_source),
        terminal_g_pct=mk(3.0, "Long-term India GDP / fuel demand proxy"),
        brent_usd=mk(69.04, "IOCL AR FY26 avg Brent"),
        capex_scale_pct=mk(100.0, "FY26 Capex Baseline"),
        production_decline_pct=mk(-2.0, "Refining & Marketing throughput growth"),
        holdco_discount_pct=mk(0.0, "Illustrative assumption"),
        exit_ev_ebitda=mk(6.0, "Downstream OMC peer EV/EBITDA"),
        as_of=as_of,
        run_id="run_iocl",
        shares_outstanding=mk(round(shares_cr, 4), "IOCL AR FY26 (1,412.1238 Cr shares)"),
        listed_investments_inr_cr=mk(inv_listed, "SSOT BS.INVESTMENTS_NC"),
        unlisted_investments_inr_cr=mk(inv_unlisted, "SSOT BS.INVESTMENTS_C"),
        cash_and_equivalents_inr_cr=mk(cce, "SSOT BS.CCE"),
        srf_deposits_inr_cr=mk(srf, "SSOT"),
        decom_provision_inr_cr=mk(decom, "SSOT"),
        borrowings_inr_cr=mk(borrowings, "SSOT BS.BORROWINGS"),
        lease_liab_inr_cr=mk(lease, "SSOT BS.LEASE_LIAB"),
        vol_crude_mmt=mk(throughput, "ssot_refinery_economics_360 FY26"),
        vol_gas_bcm=mk(0.0, "N/A Downstream"),
        bbl_per_tonne=mk(7.33, "Constant"),
        gcv_mmbtu_per_scm=mk(0.0372, "Constant"),
        fx_inr_usd=mk(88.37, "RBI / AR FY26 average FX"),
        crude_realisation_discount_pct=mk(0.0, "AR"),
        gas_price_usd_mmbtu=mk(0.0, "N/A Downstream"),
        vap_revenue_ratio=mk(0.055, "Petchem / Pipelines mix"),
        effective_levy_rate=mk(0.115, "Ind AS 115 Excise / Gross ratio"),
        opex_per_boe=mk(4.85, "Refinery & marketing opex $/bbl"),
        inflation_pct=mk(4.0, "Illustrative"),
        exploration_writeoff_ratio=mk(0.0, "Downstream OMC"),
        dd_a_ratio=mk(0.50, "DD&A / Capex ratio"),
        tax_rate_pct=mk(25.17, "Sec 115BAA AR FY26"),
        capex_base_inr_cr=mk(capex_base, "CAPEX.TOTAL FY26"),
        nwc_pct=mk(0.02, "Derived"),
        market_price_inr=mk(mkt_px, mkt_src),
        grm_usd_bbl=grm,
        refining_throughput_mmt=throughput,
        marketing_sales_mmt=mkt_vol,
        base_fcff_inr_cr=round(base_fcf, 2),
    )
