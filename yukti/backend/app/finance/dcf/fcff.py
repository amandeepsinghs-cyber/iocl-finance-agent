# fcff.py
def compute_fcff(assumptions):
    if assumptions.forecast_fcff:
        fcff_list = assumptions.forecast_fcff
        res = []
        for i, f in enumerate(fcff_list, 1):
            res.append({
                "period": f"FY{26+i}",
                "fcff": f,
                "t": i,
                "discount_factor": 1 / ((1 + assumptions.wacc_pct.value / 100) ** i),
                "pv_fcff": f / ((1 + assumptions.wacc_pct.value / 100) ** i)
            })
        return {"forecast": res, "historical": []}

    res = []
    w = assumptions.wacc_pct.value / 100
    grm_usd = getattr(assumptions, "grm_usd_bbl", 0.0) or 0.0
    if grm_usd > 0.0:
        # Downstream IOCL OMC FCFF path: Refinery Throughput (MMT) * GRM ($/bbl) + Marketing & Pipeline EBITDA - DD&A - Tax - Capex
        tp_base = float(getattr(assumptions, "refining_throughput_mmt", 0.0) or assumptions.vol_crude_mmt.value or 75.451)
        mkt_base = float(getattr(assumptions, "marketing_sales_mmt", 0.0) or 105.117)
        vol_growth = -(assumptions.production_decline_pct.value / 100.0)
        capex_base = assumptions.capex_base_inr_cr.value * (assumptions.capex_scale_pct.value / 100.0)
        # Scale FY26 base EBITDA (₹74,243.42 Cr) across throughput, GRM ($10.85/bbl baseline), Brent & FX
        brent_scale = (assumptions.brent_usd.value / 69.04) if assumptions.brent_usd.value > 0 else 1.0
        fx_scale = (assumptions.fx_inr_usd.value / 88.37) if assumptions.fx_inr_usd.value > 0 else 1.0
        for i in range(1, 11):
            g_mult = (1.0 + vol_growth) ** i
            inf_mult = (1.0 + assumptions.inflation_pct.value / 100.0) ** i
            tp = tp_base * g_mult
            refining_ebitda = tp * assumptions.bbl_per_tonne.value * grm_usd * assumptions.fx_inr_usd.value / 10.0 * 0.58
            mkt_pipe_petchem_ebitda = (41250.0 * g_mult * (0.95 + 0.05 * brent_scale))
            ebitda = (refining_ebitda + mkt_pipe_petchem_ebitda) * (0.5 + 0.5 * fx_scale)
            capex = capex_base * (1.0 + 0.02 * i)
            dda = 16964.82 * (1.0 + 0.03 * i)
            ebit = ebitda - dda
            tax = max(ebit, 0.0) * (assumptions.tax_rate_pct.value / 100.0)
            rev = 784157.87 * g_mult * brent_scale * fx_scale
            nwc = rev * 0.004 * (inf_mult / (1.0 + assumptions.inflation_pct.value / 100.0) ** (i - 1) - 1.0)
            fcff = ebit - tax + dda - capex - nwc
            res.append({
                "period": f"FY{26+i}",
                "throughput_mmt": round(tp, 2),
                "marketing_mmt": round(mkt_base * g_mult, 2),
                "rev": round(rev, 2),
                "opex": round(57600.40 * inf_mult, 2),
                "capex": round(capex, 2),
                "dda": round(dda, 2),
                "ebit": round(ebit, 2),
                "tax": round(tax, 2),
                "nwc": round(nwc, 2),
                "fcff": round(fcff, 2),
                "t": i,
                "discount_factor": 1 / ((1 + w) ** i),
                "pv_fcff": round(fcff / ((1 + w) ** i), 2),
            })
        return {"forecast": res, "historical": []}

    for i in range(1, 11):
        crude_vol = assumptions.vol_crude_mmt.value * ((1 - assumptions.production_decline_pct.value/100)**i)
        gas_vol = assumptions.vol_gas_bcm.value * ((1 - assumptions.production_decline_pct.value/100)**i)
        rev_crude = crude_vol * assumptions.bbl_per_tonne.value * assumptions.brent_usd.value * assumptions.fx_inr_usd.value / 10
        rev_gas = gas_vol * 100.0 * assumptions.gcv_mmbtu_per_scm.value * assumptions.gas_price_usd_mmbtu.value * assumptions.fx_inr_usd.value
        rev_vap = (rev_crude + rev_gas) * assumptions.vap_revenue_ratio.value
        rev = rev_crude + rev_gas + rev_vap
        
        levy = rev * assumptions.effective_levy_rate.value
        boe = (crude_vol * 7.33 + gas_vol * 6.29) * 1e6
        opex = (boe * assumptions.opex_per_boe.value * assumptions.fx_inr_usd.value / 1e7) * ((1 + assumptions.inflation_pct.value/100)**i)
        
        capex = assumptions.capex_base_inr_cr.value * (assumptions.capex_scale_pct.value/100)
        dda = capex * assumptions.dd_a_ratio.value
        expl = capex * assumptions.exploration_writeoff_ratio.value
        
        ebit = rev - levy - opex - dda - expl
        tax = ebit * (assumptions.tax_rate_pct.value / 100)
        nwc = rev * assumptions.nwc_pct.value - (rev / (1+assumptions.inflation_pct.value/100)) * assumptions.nwc_pct.value
        
        fcff = ebit - tax + dda - capex - nwc
        
        res.append({
            "period": f"FY{26+i}",
            "crude_mmt": crude_vol,
            "gas_bcm": gas_vol,
            "rev_crude": rev_crude,
            "rev_gas": rev_gas,
            "rev_vap": rev_vap,
            "rev": rev,
            "levy": levy,
            "opex": opex,
            "capex": capex,
            "dda": dda,
            "expl": expl,
            "ebit": ebit,
            "tax": tax,
            "nwc": nwc,
            "fcff": fcff,
            "t": i,
            "discount_factor": 1 / ((1+w)**i),
            "pv_fcff": fcff / ((1+w)**i)
        })

    return {"forecast": res, "historical": []}
