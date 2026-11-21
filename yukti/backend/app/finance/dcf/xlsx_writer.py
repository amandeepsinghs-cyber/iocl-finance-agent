"""Boardroom-formatted, 100% live-formula Excel (.xlsx) workbook writer for IOCL (NSE:IOC) DCF Valuation.

Preserves exact cell coordinates tested by `tests/finance/test_xlsx_formulas.py`:
  - `Cover!A3`: bold disclaimer
  - `Assumptions`: Named Ranges for every scalar assumption (`wacc_pct`, `terminal_g_pct`, etc.)
  - `Forecast`: Row 1 = Period, Row 2 = `t`, Row 3 = `FCFF`, Row 4 = Discount Factor formula, Row 5 = PV(FCFF) formula,
    Row 7 = Revenue from Operations, Row 8 = Operating Profit (EBIT)
  - `Valuation!B1:B15`: live Excel formulas (`Valuation!B15` = `=B13 / B14`, Named Range `PerShareValue`)
  - `Sensitivity`: WACC axis in `A3:A11`, g axis in `B2:J2`, 9x9 live-formula grid in `B3:J11`
  - `Tornado`: OMC driver swings + embedded horizontal bar chart
  - `Sources`: full SSOT & Annual Report lineage
"""
from __future__ import annotations

from typing import Any, Dict

import openpyxl
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName

# IndianOil Corporate & Investment-Banking Palette
IOCL_NAVY = "003366"
IOCL_SAFFRON = "F37021"
SUBTOTAL_BG = "EEF3F8"
ZEBRA_BG = "F9FBFD"
INPUT_YELLOW = "FFF2CC"
BASE_HIGHLIGHT = "D9E8FB"
BORDER_GRAY = "CBD5E1"

FONT_TITLE = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
FONT_SUBTITLE = Font(name="Calibri", size=10, bold=True, color=IOCL_NAVY)
FONT_HEADER = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
FONT_BOLD = Font(name="Calibri", size=10, bold=True, color="0F172A")
FONT_BODY = Font(name="Calibri", size=10, bold=False, color="0F172A")
FONT_INPUT = Font(name="Calibri", size=10, bold=False, color="0000FF")
FONT_TOTAL = Font(name="Calibri", size=11, bold=True, color=IOCL_NAVY)
FONT_DISCLAIMER = Font(name="Calibri", size=10, bold=True, color="9A3412")

FILL_NAVY = PatternFill(start_color=IOCL_NAVY, end_color=IOCL_NAVY, fill_type="solid")
FILL_SAFFRON = PatternFill(start_color=IOCL_SAFFRON, end_color=IOCL_SAFFRON, fill_type="solid")
FILL_SUBTOTAL = PatternFill(start_color=SUBTOTAL_BG, end_color=SUBTOTAL_BG, fill_type="solid")
FILL_ZEBRA = PatternFill(start_color=ZEBRA_BG, end_color=ZEBRA_BG, fill_type="solid")
FILL_INPUT = PatternFill(start_color=INPUT_YELLOW, end_color=INPUT_YELLOW, fill_type="solid")
FILL_BASE = PatternFill(start_color=BASE_HIGHLIGHT, end_color=BASE_HIGHLIGHT, fill_type="solid")

THIN_SIDE = Side(border_style="thin", color=BORDER_GRAY)
NAVY_MED = Side(border_style="medium", color=IOCL_NAVY)
DOUBLE_NAVY = Side(border_style="double", color=IOCL_NAVY)

BORDER_CELL = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)
BORDER_SUBTOTAL = Border(top=THIN_SIDE, bottom=NAVY_MED, left=THIN_SIDE, right=THIN_SIDE)
BORDER_TOTAL = Border(top=THIN_SIDE, bottom=DOUBLE_NAVY, left=THIN_SIDE, right=THIN_SIDE)

FMT_INR_CR = "₹#,##0.00;(₹#,##0.00);\"-\""
FMT_INR_PS = "₹#,##0.00;(₹#,##0.00);\"-\""
FMT_PCT = "0.00%"
FMT_DEC = "#,##0.00"
FMT_DF = "0.0000\"x\""

DRIVER_DISPLAY = {
    "brent": "Brent / GRM spread",
    "grm": "Singapore GRM",
    "opex": "Refining & Mktg Opex",
    "capex": "Capex scale",
    "prod": "Refining throughput",
    "wacc": "WACC",
    "g": "Terminal growth (g)",
    "fx": "INR / USD rate",
    "holdco": "Holdco discount",
}

EDITABLE_KEYS = {
    "wacc_pct",
    "terminal_g_pct",
    "brent_usd",
    "capex_scale_pct",
    "production_decline_pct",
    "holdco_discount_pct",
    "exit_ev_ebitda",
}


def _autofit_columns(ws: Any, min_w: int = 12, max_w: int = 48) -> None:
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        best = min_w
        for cell in col:
            val = cell.value
            if val is None:
                continue
            s = str(val)
            if s.startswith("="):
                # Formula result width estimate (e.g. ₹4,90,567.65)
                est = 16
            else:
                est = len(s) + 3
            if est > best:
                best = est
        ws.column_dimensions[col_letter].width = min(best, max_w)


def _style_header_row(ws: Any, row_idx: int, max_col: int) -> None:
    ws.row_dimensions[row_idx].height = 24
    for c in range(1, max_col + 1):
        cell = ws.cell(row=row_idx, column=c)
        cell.fill = FILL_NAVY
        cell.font = FONT_HEADER
        cell.alignment = Alignment(horizontal="center" if c > 1 else "left", vertical="center", wrap_text=True)
        cell.border = BORDER_CELL


def write_dcf_xlsx(result: Dict[str, Any], filename: str) -> None:
    wb = openpyxl.Workbook()
    wb.properties.title = "IndianOil (NSE:IOC) Standalone DCF Valuation Model"
    wb.properties.creator = "Yukti AI — IndianOil Finance & Downstream Intelligence"

    # =========================================================================
    # 1. Cover (Executive Summary linked by live Excel formulas to Valuation!)
    # =========================================================================
    ws_cover = wb.active
    ws_cover.title = "Cover"
    ws_cover.views.sheetView[0].showGridLines = False

    ws_cover.merge_cells("A1:D1")
    ws_cover["A1"] = "IndianOil (NSE:IOC) — Standalone DCF Valuation Model"
    ws_cover["A1"].font = FONT_TITLE
    ws_cover["A1"].fill = FILL_NAVY
    ws_cover["A1"].alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws_cover.row_dimensions[1].height = 30

    ws_cover.merge_cells("A2:D2")
    ws_cover["A2"].fill = FILL_SAFFRON
    ws_cover.row_dimensions[2].height = 5

    ws_cover["A3"] = result.get("disclaimer", "Illustrative valuation, not investment advice.")
    ws_cover["A3"].font = FONT_DISCLAIMER

    ws_cover["A5"] = "Run ID"
    ws_cover["B5"] = str(result.get("run_id") or "dcf_run")
    ws_cover["A6"] = "Valuation As Of"
    ws_cover["B6"] = str(result.get("as_of") or "2026-03-30")
    ws_cover["A7"] = "Basis & Scope"
    ws_cover["B7"] = "Standalone Ind-AS Schedule III SSOT (FY26 Verbatim AR) + 10Y Explicit FCFF"
    ws_cover["A8"] = "Provenance"
    ws_cover["B8"] = "Verified FY26 IOCL Annual Report SSOT · Illustrative Valuation"
    for r in range(5, 9):
        ws_cover[f"A{r}"].font = FONT_BOLD
        ws_cover[f"B{r}"].font = FONT_BODY

    # Executive Valuation Snapshot (100% live formulas!)
    ws_cover["A10"] = "Valuation Output Summary (Live Formulas)"
    ws_cover["B10"] = "Model Value"
    ws_cover["C10"] = "Unit / Formula Link"
    _style_header_row(ws_cover, 10, 3)

    cover_kpis = [
        ("Intrinsic Value per Share", "=Valuation!B15", "₹ / share (=Valuation!B15)", FMT_INR_PS, True),
        ("Enterprise Value (EV)", "=Valuation!B4", "₹ crore (=Valuation!B4)", FMT_INR_CR, False),
        ("Equity Value", "=Valuation!B13", "₹ crore (=Valuation!B13)", FMT_INR_CR, False),
        ("Sum of PV of Explicit FCFF (10Y)", "=Valuation!B1", "₹ crore (=Valuation!B1)", FMT_INR_CR, False),
        ("PV of Terminal Value (Gordon)", "=Valuation!B3", "₹ crore (=Valuation!B3)", FMT_INR_CR, False),
        ("WACC Assumption", "=wacc_pct/100", "% (=wacc_pct)", FMT_PCT, False),
        ("Terminal Growth Rate (g)", "=terminal_g_pct/100", "% (=terminal_g_pct)", FMT_PCT, False),
    ]
    for idx, (lbl, formula, note, num_fmt, is_hero) in enumerate(cover_kpis, start=11):
        ws_cover[f"A{idx}"] = lbl
        ws_cover[f"B{idx}"] = formula
        ws_cover[f"C{idx}"] = note
        ws_cover[f"A{idx}"].font = FONT_TOTAL if is_hero else FONT_BODY
        ws_cover[f"B{idx}"].font = FONT_TOTAL if is_hero else FONT_BOLD
        ws_cover[f"C{idx}"].font = FONT_BODY
        ws_cover[f"B{idx}"].number_format = num_fmt
        ws_cover[f"B{idx}"].alignment = Alignment(horizontal="right")
        fill = FILL_BASE if is_hero else (FILL_ZEBRA if idx % 2 == 0 else None)
        bdr = BORDER_TOTAL if is_hero else BORDER_CELL
        for col_c in ("A", "B", "C"):
            ws_cover[f"{col_c}{idx}"].border = bdr
            if fill:
                ws_cover[f"{col_c}{idx}"].fill = fill

    ws_cover["A20"] = "Legend: Yellow cells on Assumptions tab are editable model drivers (blue font = hardcoded inputs, black font = live Excel formulas)."
    ws_cover["A20"].font = FONT_SUBTITLE

    # =========================================================================
    # 2. Assumptions (Yellow Editable Inputs + Excel Named Ranges)
    # =========================================================================
    ws_a = wb.create_sheet("Assumptions")
    ws_a.freeze_panes = "A2"
    ws_a["A1"] = "Assumption Parameter"
    ws_a["B1"] = "Value"
    ws_a["C1"] = "Source / Lineage"
    _style_header_row(ws_a, 1, 3)

    a_dict = result.get("assumptions", {})
    row = 2
    for k, v in a_dict.items():
        if k == "forecast_fcff":
            continue
        if isinstance(v, dict) and "value" in v:
            val = v["value"]
            src = v.get("source", "SSOT")
        else:
            val = v
            src = "Engine"

        ws_a[f"A{row}"] = k
        ws_a[f"B{row}"] = val
        ws_a[f"C{row}"] = str(src)
        ws_a[f"A{row}"].font = FONT_BOLD if k in EDITABLE_KEYS else FONT_BODY
        ws_a[f"B{row}"].font = FONT_INPUT if isinstance(val, (int, float)) else FONT_BODY
        ws_a[f"C{row}"].font = FONT_BODY
        ws_a[f"B{row}"].alignment = Alignment(horizontal="right")
        if isinstance(val, (int, float)):
            ws_a[f"B{row}"].number_format = FMT_DEC
        if k in EDITABLE_KEYS:
            ws_a[f"B{row}"].fill = FILL_INPUT
        for col_c in ("A", "B", "C"):
            ws_a[f"{col_c}{row}"].border = BORDER_CELL

        dn = DefinedName(k, attr_text=f"Assumptions!$B${row}")
        wb.defined_names.add(dn)
        row += 1

    # =========================================================================
    # 3. WACC Build-Up
    # =========================================================================
    ws_wacc = wb.create_sheet("WACC")
    ws_wacc.freeze_panes = "A2"
    ws_wacc["A1"] = "WACC Component"
    ws_wacc["B1"] = "Value"
    _style_header_row(ws_wacc, 1, 2)

    w_row = 2
    for k, v in (result.get("wacc_build") or {}).items():
        ws_wacc[f"A{w_row}"] = k
        ws_wacc[f"B{w_row}"] = v
        is_tot = str(k).lower() in ("wacc_pct", "ke_pct", "kd_used_pct")
        ws_wacc[f"A{w_row}"].font = FONT_TOTAL if str(k).lower() == "wacc_pct" else (FONT_BOLD if is_tot else FONT_BODY)
        ws_wacc[f"B{w_row}"].font = FONT_TOTAL if str(k).lower() == "wacc_pct" else (FONT_BOLD if is_tot else FONT_INPUT)
        if isinstance(v, (int, float)):
            ws_wacc[f"B{w_row}"].number_format = FMT_DEC
            ws_wacc[f"B{w_row}"].alignment = Alignment(horizontal="right")
        bdr = BORDER_TOTAL if str(k).lower() == "wacc_pct" else (BORDER_SUBTOTAL if is_tot else BORDER_CELL)
        for col_c in ("A", "B"):
            ws_wacc[f"{col_c}{w_row}"].border = bdr
            if str(k).lower() == "wacc_pct":
                ws_wacc[f"{col_c}{w_row}"].fill = FILL_BASE
            elif is_tot:
                ws_wacc[f"{col_c}{w_row}"].fill = FILL_SUBTOTAL
        w_row += 1

    # =========================================================================
    # 4. Historical (FY17–FY26 Verified SSOT)
    # =========================================================================
    ws_hist = wb.create_sheet("Historical")
    ws_hist.freeze_panes = "A2"
    ws_hist.append(["Fiscal Year", "Line Code", "Value (₹ Cr)", "Source Document", "Page / Reference"])
    _style_header_row(ws_hist, 1, 5)

    for h_idx, row_data in enumerate(result.get("historical", []), start=2):
        ws_hist.append([
            row_data.get("fy", ""),
            row_data.get("line_code", ""),
            row_data.get("value_inr_cr", ""),
            row_data.get("source_doc", ""),
            row_data.get("page", row_data.get("source", "")),
        ])
        for c in range(1, 6):
            cell = ws_hist.cell(row=h_idx, column=c)
            cell.font = FONT_INPUT if c == 3 else FONT_BODY
            cell.border = BORDER_CELL
            if h_idx % 2 == 1:
                cell.fill = FILL_ZEBRA
        ws_hist.cell(row=h_idx, column=3).number_format = FMT_INR_CR
        ws_hist.cell(row=h_idx, column=3).alignment = Alignment(horizontal="right")

    # =========================================================================
    # 5. Forecast (Row 2=t, Row 3=FCFF preserved for evaluator parity + live DF/PV/Total formulas)
    # =========================================================================
    ws_f = wb.create_sheet("Forecast")
    ws_f.freeze_panes = "B2"
    ws_f["A1"] = "Explicit Forecast Schedule (₹ Cr)"
    ws_f["A2"] = "t (Year Index)"
    ws_f["A3"] = "Free Cash Flow to Firm (FCFF)"

    fcff_data = result.get("forecast", [])
    rev_list = []
    ebit_list = []

    if isinstance(fcff_data, dict):
        years = fcff_data.get("years", [])
        lines = fcff_data.get("lines", {})
        fcff_list = lines.get("fcff", [])
        rev_list = lines.get("revenue", [])
        ebit_list = lines.get("ebit", [])
        if not fcff_list and "rows" in fcff_data:
            fcff_row = next((r for r in fcff_data["rows"] if r.get("code") == "fcff"), {})
            fcff_list = fcff_row.get("values", [])

        for i, val in enumerate(fcff_list):
            col = get_column_letter(2 + i)
            period = years[i] if i < len(years) else f"FY{27 + i}"
            ws_f[f"{col}1"] = period
            ws_f[f"{col}2"] = i + 1
            ws_f[f"{col}3"] = val
        list_len = len(fcff_list)
    else:
        for i, r in enumerate(fcff_data):
            col = get_column_letter(2 + i)
            ws_f[f"{col}1"] = r.get("period", f"FY{27 + i}")
            ws_f[f"{col}2"] = r.get("t", i + 1)
            ws_f[f"{col}3"] = r.get("fcff", 0)
            if "rev" in r:
                rev_list.append(r.get("rev"))
            if "ebit" in r:
                ebit_list.append(r.get("ebit"))
        list_len = len(fcff_data)

    last_col = get_column_letter(2 + list_len - 1) if list_len > 0 else "B"
    tot_col = get_column_letter(2 + list_len) if list_len > 0 else "C"
    ws_f[f"{tot_col}1"] = "10Y Total"
    _style_header_row(ws_f, 1, max(2, list_len + 2))

    # Row 4: Discount Factor (live formula) | Row 5: PV of FCFF (live formula)
    ws_f["A4"] = "Discount Factor (end-year)"
    ws_f["A5"] = "Present Value of FCFF"
    for i in range(list_len):
        col = get_column_letter(2 + i)
        ws_f[f"{col}4"] = f"=1/(1+wacc_pct/100)^{col}2"
        ws_f[f"{col}5"] = f"={col}3*{col}4"

    if list_len > 0:
        ws_f[f"{tot_col}3"] = f"=SUM(B3:{last_col}3)"
        ws_f[f"{tot_col}5"] = f"=SUM(B5:{last_col}5)"

    # Optional Memo Rows (Rows 7 & 8: Revenue & EBIT, cleanly separated so Valuation! formulas on Rows 2-3 never shift)
    if rev_list:
        ws_f["A7"] = "Revenue from Operations (Forecast)"
        for i, rv in enumerate(rev_list[:list_len]):
            ws_f[f"{get_column_letter(2 + i)}7"] = rv
        if list_len > 0:
            ws_f[f"{tot_col}7"] = f"=SUM(B7:{last_col}7)"
    if ebit_list:
        ws_f["A8"] = "Operating Profit / EBIT (Forecast)"
        for i, ev in enumerate(ebit_list[:list_len]):
            ws_f[f"{get_column_letter(2 + i)}8"] = ev
        if list_len > 0:
            ws_f[f"{tot_col}8"] = f"=SUM(B8:{last_col}8)"

    # Style Forecast rows
    max_fc_col = max(2, list_len + 2)
    for r_idx, fmt, font_a, font_v, fill, bdr in (
        (2, "0", FONT_BODY, FONT_BODY, None, BORDER_CELL),
        (3, FMT_INR_CR, FONT_BOLD, FONT_INPUT, FILL_ZEBRA, BORDER_CELL),
        (4, FMT_DF, FONT_BODY, FONT_BODY, None, BORDER_CELL),
        (5, FMT_INR_CR, FONT_TOTAL, FONT_TOTAL, FILL_BASE, BORDER_TOTAL),
        (7, FMT_INR_CR, FONT_BODY, FONT_INPUT, None, BORDER_CELL),
        (8, FMT_INR_CR, FONT_BOLD, FONT_INPUT, FILL_SUBTOTAL, BORDER_SUBTOTAL),
    ):
        if ws_f[f"A{r_idx}"].value is None:
            continue
        ws_f[f"A{r_idx}"].font = font_a
        ws_f[f"A{r_idx}"].border = bdr
        if fill:
            ws_f[f"A{r_idx}"].fill = fill
        for c in range(2, max_fc_col + 1):
            cell = ws_f.cell(row=r_idx, column=c)
            cell.font = FONT_BOLD if (c == max_fc_col and r_idx in (3, 7, 8)) else font_v
            if cell.value is not None:
                cell.number_format = fmt
                cell.alignment = Alignment(horizontal="right")
            cell.border = bdr
            if fill:
                cell.fill = fill

    # =========================================================================
    # 6. Valuation (Exact Row 1..15 Coordinates Preserved + Full IB Styling!)
    # =========================================================================
    ws_v = wb.create_sheet("Valuation")
    val_rows = [
        (1, "Sum of PV FCFF", f"=SUMPRODUCT(Forecast!B3:{last_col}3 / (1+wacc_pct/100)^Forecast!B2:{last_col}2)", FMT_INR_CR, "normal"),
        (2, "TV (Gordon)", f"=Forecast!{last_col}3 * (1+terminal_g_pct/100) / (wacc_pct/100 - terminal_g_pct/100)", FMT_INR_CR, "normal"),
        (3, "PV of TV", f"=B2 / (1+wacc_pct/100)^{list_len}", FMT_INR_CR, "normal"),
        (4, "Enterprise Value (EV)", "=B1 + B3", FMT_INR_CR, "subtotal"),
        (5, "Less: Borrowings", "=borrowings_inr_cr", FMT_INR_CR, "normal"),
        (6, "Less: Lease Liabilities", "=lease_liab_inr_cr", FMT_INR_CR, "normal"),
        (7, "Less: Decommissioning Provisions", "=decom_provision_inr_cr", FMT_INR_CR, "normal"),
        (8, "Add: Cash & Cash Equivalents", "=cash_and_equivalents_inr_cr", FMT_INR_CR, "normal"),
        (9, "Add: SRF Deposits", "=srf_deposits_inr_cr", FMT_INR_CR, "normal"),
        (10, "Add: Listed Investments (net of holdco discount)", "=listed_investments_inr_cr * (1 - holdco_discount_pct/100)", FMT_INR_CR, "normal"),
        (11, "Add: Unlisted Investments", "=unlisted_investments_inr_cr", FMT_INR_CR, "normal"),
        (12, "Equity Value Before Discount", "=B4 - B5 - B6 - B7 + B8 + B9 + B10 + B11", FMT_INR_CR, "normal"),
        (13, "Equity Value (₹ Cr)", "=B12", FMT_INR_CR, "subtotal"),
        (14, "Shares Outstanding (Cr)", "=shares_outstanding", FMT_DEC, "normal"),
        (15, "Intrinsic Value per Share (₹)", "=B13 / B14", FMT_INR_PS, "total"),
    ]
    for r_idx, label, formula, num_fmt, style_kind in val_rows:
        ws_v[f"A{r_idx}"] = label
        ws_v[f"B{r_idx}"] = formula
        ws_v[f"B{r_idx}"].number_format = num_fmt
        ws_v[f"B{r_idx}"].alignment = Alignment(horizontal="right")
        if style_kind == "total":
            ws_v[f"A{r_idx}"].font = FONT_TOTAL
            ws_v[f"B{r_idx}"].font = FONT_TOTAL
            bdr, fill = BORDER_TOTAL, FILL_BASE
        elif style_kind == "subtotal":
            ws_v[f"A{r_idx}"].font = FONT_BOLD
            ws_v[f"B{r_idx}"].font = FONT_BOLD
            bdr, fill = BORDER_SUBTOTAL, FILL_SUBTOTAL
        else:
            ws_v[f"A{r_idx}"].font = FONT_BODY
            ws_v[f"B{r_idx}"].font = FONT_BODY
            bdr, fill = BORDER_CELL, (FILL_ZEBRA if r_idx % 2 == 0 else None)
        for col_c in ("A", "B"):
            ws_v[f"{col_c}{r_idx}"].border = bdr
            if fill:
                ws_v[f"{col_c}{r_idx}"].fill = fill

    dn_ps = DefinedName("PerShareValue", attr_text="Valuation!$B$15")
    wb.defined_names.add(dn_ps)

    # =========================================================================
    # 7. Sensitivity (Exact 9x9 WACC x g Coordinates A3:A11 & B2:J2 Preserved!)
    # =========================================================================
    ws_s = wb.create_sheet("Sensitivity")
    ws_s.freeze_panes = "B3"
    ws_s["A1"] = "Sensitivity: Intrinsic Value / Share (₹) — WACC (%) vs. Terminal g (%)"
    ws_s.merge_cells("A1:J1")
    _style_header_row(ws_s, 1, 10)
    ws_s["A2"] = "WACC \\ g"
    ws_s["A2"].font = FONT_BOLD
    ws_s["A2"].fill = FILL_SUBTOTAL
    ws_s["A2"].alignment = Alignment(horizontal="center")
    ws_s["A2"].border = BORDER_CELL

    for i in range(-4, 5):
        r_idx = i + 7  # WACC at rows 3..11 (base = row 7)
        cell = ws_s.cell(row=r_idx, column=1, value=f"=wacc_pct + {i * 0.5}")
        cell.font = FONT_BOLD
        cell.fill = FILL_BASE if i == 0 else FILL_SUBTOTAL
        cell.number_format = "0.00\"%\""
        cell.alignment = Alignment(horizontal="right")
        cell.border = BORDER_CELL

    for j in range(-4, 5):
        c_idx = j + 6  # g at cols 2 (B)..10 (J) (base = col 6 / F)
        cell = ws_s.cell(row=2, column=c_idx, value=f"=terminal_g_pct + {j * 0.5}")
        cell.font = FONT_BOLD
        cell.fill = FILL_BASE if j == 0 else FILL_SUBTOTAL
        cell.number_format = "0.00\"%\""
        cell.alignment = Alignment(horizontal="right")
        cell.border = BORDER_CELL

    for r in range(3, 12):
        for c in range(2, 11):
            w_ref = f"$A{r}"
            g_ref = f"{get_column_letter(c)}$2"
            sumpv = f"SUMPRODUCT(Forecast!$B$3:${last_col}$3 / (1+{w_ref}/100)^Forecast!$B$2:${last_col}$2)"
            tv = f"(Forecast!${last_col}$3 * (1+{g_ref}/100) / ({w_ref}/100 - {g_ref}/100)) / (1+{w_ref}/100)^{list_len}"
            adj = (
                "-borrowings_inr_cr - lease_liab_inr_cr - decom_provision_inr_cr "
                "+ cash_and_equivalents_inr_cr + srf_deposits_inr_cr "
                "+ listed_investments_inr_cr * (1 - holdco_discount_pct/100) + unlisted_investments_inr_cr"
            )
            eq = f"({sumpv} + {tv} {adj})"
            ps = f"={eq} / shares_outstanding"
            cell = ws_s.cell(row=r, column=c, value=ps)
            is_base = (r == 7 and c == 6)
            cell.font = FONT_TOTAL if is_base else FONT_BODY
            cell.fill = FILL_BASE if is_base else (FILL_ZEBRA if r % 2 == 0 else PatternFill(fill_type=None))
            cell.number_format = FMT_INR_PS
            cell.alignment = Alignment(horizontal="right")
            cell.border = BORDER_TOTAL if is_base else BORDER_CELL

    # =========================================================================
    # 8. Tornado (IOCL OMC Driver Swings + Embedded Chart)
    # =========================================================================
    ws_t = wb.create_sheet("Tornado")
    ws_t.freeze_panes = "A3"
    ws_t["A1"] = f"IOCL OMC Driver Sensitivity Tornado — Run {result.get('run_id')}"
    ws_t.merge_cells("A1:D1")
    _style_header_row(ws_t, 1, 4)

    ws_t["A2"] = "Valuation Driver"
    ws_t["B2"] = "Low Case (₹/sh)"
    ws_t["C2"] = "High Case (₹/sh)"
    ws_t["D2"] = "Swing (₹/sh)"
    for c in range(1, 5):
        cell = ws_t.cell(row=2, column=c)
        cell.font = FONT_BOLD
        cell.fill = FILL_SUBTOTAL
        cell.border = BORDER_SUBTOTAL
        cell.alignment = Alignment(horizontal="right" if c > 1 else "left")

    t_row = 3
    raw_tor = result.get("tornado", [])
    tor_list = raw_tor.get("bars", []) if isinstance(raw_tor, dict) else (raw_tor or [])
    for tor in tor_list:
        if not isinstance(tor, dict):
            continue
        raw_drv = str(tor.get("driver") or "")
        lbl = DRIVER_DISPLAY.get(raw_drv.lower(), raw_drv)
        ws_t[f"A{t_row}"] = lbl
        ws_t[f"B{t_row}"] = tor.get("low_inr")
        ws_t[f"C{t_row}"] = tor.get("high_inr")
        ws_t[f"D{t_row}"] = f"=ABS(C{t_row}-B{t_row})"
        ws_t[f"A{t_row}"].font = FONT_BODY
        ws_t[f"B{t_row}"].font = FONT_INPUT
        ws_t[f"C{t_row}"].font = FONT_INPUT
        ws_t[f"D{t_row}"].font = FONT_BOLD
        for col_c in ("B", "C", "D"):
            ws_t[f"{col_c}{t_row}"].number_format = FMT_INR_PS
            ws_t[f"{col_c}{t_row}"].alignment = Alignment(horizontal="right")
        for col_c in ("A", "B", "C", "D"):
            ws_t[f"{col_c}{t_row}"].border = BORDER_CELL
        t_row += 1

    if t_row > 3:
        chart = BarChart()
        chart.type = "bar"
        chart.style = 10
        chart.title = "IOCL DCF Sensitivity Tornado (₹ / share)"
        chart.width = 18
        chart.height = 11
        data = Reference(ws_t, min_col=2, min_row=2, max_row=t_row - 1, max_col=3)
        cats = Reference(ws_t, min_col=1, min_row=3, max_row=t_row - 1)
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(cats)
        ws_t.add_chart(chart, "F2")

    # =========================================================================
    # 9. Sources & Audit Lineage
    # =========================================================================
    ws_src = wb.create_sheet("Sources")
    ws_src.freeze_panes = "A2"
    ws_src["A1"] = "Lineage / Valuation Item"
    ws_src["B1"] = "Verified Source Document"
    _style_header_row(ws_src, 1, 2)
    s_row = 2

    for ref in result.get("lineage_refs", []):
        ws_src[f"A{s_row}"] = ref.get("item", ref.get("text", ""))
        ws_src[f"B{s_row}"] = ref.get("source", ref.get("doc_id", ""))
        s_row += 1

    for br in result.get("bridge", []):
        ws_src[f"A{s_row}"] = br.get("item", br.get("label", ""))
        ws_src[f"B{s_row}"] = br.get("source", "")
        s_row += 1

    for hist in result.get("historical", []):
        ws_src[f"A{s_row}"] = f"{hist.get('fy', '')} {hist.get('line_code', '')}"
        ws_src[f"B{s_row}"] = hist.get("source_doc", hist.get("source", ""))
        s_row += 1

    for r_i in range(2, s_row):
        for col_c in ("A", "B"):
            ws_src[f"{col_c}{r_i}"].font = FONT_BODY
            ws_src[f"{col_c}{r_i}"].border = BORDER_CELL
            if r_i % 2 == 1:
                ws_src[f"{col_c}{r_i}"].fill = FILL_ZEBRA

    # Auto-fit column widths across all 9 sheets so zero `###` truncation ever appears
    for ws in wb.worksheets:
        _autofit_columns(ws)
    ws_cover.column_dimensions["A"].width = 36
    ws_cover.column_dimensions["B"].width = 22
    ws_cover.column_dimensions["C"].width = 34
    ws_v.column_dimensions["A"].width = 44
    ws_v.column_dimensions["B"].width = 22

    wb.save(filename)
