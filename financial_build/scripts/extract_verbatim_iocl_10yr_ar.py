#!/usr/local/google/home/amandeepsinghs/o&g agentic transformation/Oil & Gas Agent Portfolio/cloud_run_apps/Yukti IOCL/yukti/backend/.venv/bin/python
"""
Deterministic 10-year (FY17-FY26) verbatim parser for IOCL Annual Reports.

Reads pdftotext -layout outputs from:
  knowledge/public_sources/grounding_data/text/IOCL_AR_FY2016-17.txt .. FY2025-26.txt

Extracts and reconciles (both own_vintage AND comparative_vintage from next AR):
  1. Standalone Balance Sheet (Schedule III Assets, Equity, Liabilities)
  2. Standalone Statement of Profit & Loss (incl. Excise Duty, Impairment, Exceptional, EPS)
  3. Standalone Statement of Cash Flows (OCF, ICF, CFF, Capex PPE + CWIP, Div/Int/Lease Paid, Cash)
  4. Consolidated Balance Sheet, P&L (incl. Owners vs NCI), and Cash Flows
  5. Note 38 Segment Information (Ind AS 108: Petroleum Products, Petrochemicals, Gas, Other Business)
  6. Key Disclosures from Notes (EPS/Weighted Shares ex-Trust, Capital Commitments, Contingencies,
     R&D Spend, CSR Spend, Inventories breakup, Dividend)

Writes verified output to:
  financial_build/data/iocl_10yr_verbatim_extracted.json
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
TEXT_DIR = REPO_ROOT / "knowledge" / "public_sources" / "grounding_data" / "text"
OUT_JSON = REPO_ROOT / "financial_build" / "data" / "iocl_10yr_verbatim_extracted.json"

FYS = [f"FY{y}" for y in range(17, 27)]

AR_SPECS: Dict[str, Dict[str, Any]] = {
    "FY17": {
        "file": "IOCL_AR_FY2016-17.txt", "two_up": False, "shifted_1819": False,
        "s_bs": [140, 141], "s_pl": [142, 143], "s_cf": [146, 147],
        "c_bs": [242, 243], "c_pl": [244, 245], "c_cf": [248, 249],
        "seg": [210, 211], "eps": [193], "inv": [177], "comm_cont": [201, 202, 203, 204],
        "rnd": [221, 222], "csr": [223, 224], "div": [192],
    },
    "FY18": {
        "file": "IOCL_AR_FY2017-18.txt", "two_up": False, "shifted_1819": False,
        "s_bs": [168, 169], "s_pl": [170, 171], "s_cf": [172, 173],
        "c_bs": [276, 277], "c_pl": [278, 279], "c_cf": [280, 281],
        "seg": [250, 251], "eps": [227], "inv": [209], "comm_cont": [238, 239, 240, 241],
        "rnd": [260, 261, 262], "csr": [263], "div": [226],
    },
    "FY19": {
        "file": "IOCL_AR_FY2018-19.txt", "two_up": False, "shifted_1819": True,
        "s_bs": [174, 175], "s_pl": [176, 177], "s_cf": [178, 179],
        "c_bs": [292, 293], "c_pl": [294, 295], "c_cf": [296, 297],
        "seg": [260, 261, 262], "eps": [238], "inv": [219], "comm_cont": [250, 251, 252, 253],
        "rnd": [273, 274], "csr": [275, 276], "div": [237],
    },
    "FY20": {
        "file": "IOCL_AR_FY2019-20.txt", "two_up": True, "shifted_1819": False,
        "s_bs": [84], "s_pl": [85], "s_cf": [86, 87],
        "c_bs": [150], "c_pl": [151], "c_cf": [152, 153],
        "seg": [130, 131], "eps": [118], "inv": [107, 108], "comm_cont": [125, 126, 127],
        "rnd": [139], "csr": [140], "div": [117],
    },
    "FY21": {
        "file": "IOCL_AR_FY2020-21.txt", "two_up": True, "shifted_1819": False,
        "s_bs": [101], "s_pl": [102], "s_cf": [103],
        "c_bs": [163], "c_pl": [164], "c_cf": [165],
        "seg": [144, 145], "eps": [132], "inv": [123], "comm_cont": [139, 140, 141],
        "rnd": [153, 154], "csr": [154, 155], "div": [132],
    },
    "FY22": {
        "file": "IOCL_AR_FY2021-22.txt", "two_up": True, "shifted_1819": False,
        "s_bs": [105], "s_pl": [106], "s_cf": [107],
        "c_bs": [174], "c_pl": [175], "c_cf": [176],
        "seg": [151, 152], "eps": [138], "inv": [129], "comm_cont": [146, 147],
        "rnd": [160, 161], "csr": [161, 162], "div": [138],
    },
    "FY23": {
        "file": "IOCL_AR_FY2022-23.txt", "two_up": True, "shifted_1819": False,
        "s_bs": [110], "s_pl": [111], "s_cf": [112],
        "c_bs": [171], "c_pl": [172], "c_cf": [173],
        "seg": [151, 152], "eps": [140], "inv": [132], "comm_cont": [146, 147],
        "rnd": [159], "csr": [159, 160], "div": [140],
    },
    "FY24": {
        "file": "IOCL_AR_FY2023-24.txt", "two_up": True, "shifted_1819": False,
        "s_bs": [108], "s_pl": [109], "s_cf": [110],
        "c_bs": [165], "c_pl": [166], "c_cf": [167],
        "seg": [144, 145], "eps": [134], "inv": [126, 127], "comm_cont": [140, 141],
        "rnd": [152, 153], "csr": [153], "div": [134],
    },
    "FY25": {
        "file": "IOCL_AR_FY2024-25.txt", "two_up": False, "shifted_1819": False,
        "s_bs": [208, 209], "s_pl": [210, 211], "s_cf": [212, 213],
        "c_bs": [328, 329], "c_pl": [330, 331], "c_cf": [332, 333],
        "seg": [284, 285, 286, 287], "eps": [263], "inv": [247, 248], "comm_cont": [275, 276, 277],
        "rnd": [301, 302, 303], "csr": [303, 304], "div": [263],
    },
    "FY26": {
        "file": "IOCL_AR_FY2025-26.txt", "two_up": False, "shifted_1819": False,
        "s_bs": [203, 204], "s_pl": [205, 206], "s_cf": [207, 208],
        "c_bs": [319, 320], "c_pl": [321, 322], "c_cf": [323, 324],
        "seg": [277, 278, 279], "eps": [257], "inv": [241, 242], "comm_cont": [268, 269, 270],
        "rnd": [292, 293, 294], "csr": [294, 295], "div": [257],
    },
}

_SHIFT_MAP = {chr(33 + i): chr(65 + i) for i in range(26)}


def decode_fy19_text(s: str) -> str:
    """Decode custom -32 shifted glyph font tokens in FY19 AR without corrupting numbers."""
    def fix_line(line: str) -> str:
        # Strip right-margin rotated chapter tabs in FY19 AR (e.g. col >= 135)
        line = re.sub(
            r"\s{3,}(?:About the|Report|From the|Chairman’s Desk|About IndianOil|Description of|Capitals|Board of|Directors and others|Directors’|Management’s|Discussion & Analysis|Discussion F Analysis|Business|Responsibility Report|Report on Corporate|Governance|Standalone financial|Consolidated financial|statements)\s*$",
            "",
            line,
        )
        # Convert PDF glyph spaces (\x03) and control-shifted punctuation (\x04..\x1f -> +32)
        cleaned = []
        for ch in line:
            oc = ord(ch)
            if ch == "\x03":
                cleaned.append(" ")
            elif ch in ("\n", "\r", "\t"):
                cleaned.append(ch)
            elif 1 <= oc < 32:
                cleaned.append(chr(oc + 32))
            else:
                cleaned.append(ch)
        line = "".join(cleaned)

        tokens = re.split(r"(\s+)", line)
        out: List[str] = []
        for tok in tokens:
            if not tok or tok.isspace():
                out.append(tok)
                continue
            if tok in ("&", "-", "–", "(", ")", ".", ",", ":", ";", "/"):
                out.append(tok)
                continue
            if (
                re.fullmatch(r"[\(\[]?[-+]?\d[\d,\.]*[\)\]]?[,;:]?", tok)
                or re.fullmatch(r"\d{4}-\d{2,4}", tok)
                or re.fullmatch(r"[IVX]+\.", tok)
                or re.fullmatch(r"\([ivxIVXa-zA-Z0-9]+\)", tok)
            ):
                out.append(tok)
                continue
            has_shifted = (
                any(c in tok for c in "!#$%&'*+/:;=")
                or re.search(r'[A-Z0-9"(),.-][A-Z]', tok)
                or re.match(r"^[02345679][A-Z]{2}", tok)
            )
            is_all_upper_with_l = bool(
                re.fullmatch(r'[A-Z0-9"#$%&\'()*+,-./:;=]*l[A-Z0-9"#$%&\'()*+,-./:;=]*', tok)
                and any(c != "l" for c in tok)
            )
            if has_shifted or is_all_upper_with_l:
                nt: List[str] = []
                for ch in tok:
                    if ch in _SHIFT_MAP:
                        nt.append(_SHIFT_MAP[ch])
                    elif ch == "l" and is_all_upper_with_l:
                        nt.append("FI")
                    else:
                        nt.append(ch)
                w = "".join(nt)
                w = (
                    w.replace("BENElTS", "BENEFITS")
                    .replace("SIGNIlCANT", "SIGNIFICANT")
                    .replace("PROlT", "PROFIT")
                    .replace("RECLASSIlED", "RECLASSIFIED")
                    .replace("CLASSIlED", "CLASSIFIED")
                    .replace("lNANCIAL", "FINANCIAL")
                    .replace("DElCIT", "DEFICIT")
                    .replace("NonMCurrent", "Non-Current")
                    .replace("NONMCURRENT", "NON-CURRENT")
                    .replace("6II.", "VII.")
                    .replace("6III.", "VIII.")
                )
                w = re.sub(r"^6$", "V", w)
                out.append(w)
            else:
                out.append(tok)
        return re.sub(r"\bNonMCurrent\b", "Non-Current", re.sub(r"Cash\s+F\s+Cash", "Cash & Cash", "".join(out), flags=re.I), flags=re.I)

    return "\n".join(fix_line(l) for l in s.splitlines())


def split_2up_blocks(page_txt: str) -> List[str]:
    lines = page_txt.splitlines()
    maxw = max((len(l) for l in lines), default=0)
    if maxw < 190:
        return [page_txt]
    candidates: List[int] = []
    for l in lines[:35]:
        for pat in [
            r"Particulars",
            r"STANDALONE FINANCIAL",
            r"CONSOLIDATED FINANCIAL",
            r"BALANCE SHEET AS AT",
            r"STATEMENT OF PROFIT",
            r"STATEMENT OF CASH",
            r"NOTES TO ",
            r"Note\s*[-–:\s]*\d+",
        ]:
            ms = [m.start() for m in re.finditer(pat, l)]
            if len(ms) >= 2 and 95 <= ms[-1] <= maxw - 20:
                candidates.append(ms[-1])
    if candidates:
        mid_cands = [c for c in candidates if 100 <= c <= int(maxw * 0.68)]
        if mid_cands:
            split_col = min(mid_cands) - 1
            left = [l[:split_col].rstrip() for l in lines]
            right = [l[split_col:].rstrip() for l in lines]
            return ["\n".join(left), "\n".join(right)]
    sample = [l.ljust(maxw) for l in lines[4:min(len(lines), 45)]]
    best_col = None
    best_score = -1
    for col in range(int(maxw * 0.42), int(maxw * 0.62)):
        spaces = sum(1 for row in sample if row[col:col + 3] == "   ")
        if spaces > best_score:
            best_score = spaces
            best_col = col + 1
    if best_col and best_score >= max(5, int(len(sample) * 0.65)):
        return [
            "\n".join(l[:best_col].rstrip() for l in lines),
            "\n".join(l[best_col:].rstrip() for l in lines),
        ]
    return [page_txt]


AMT_RE = re.compile(
    r"(?<!\S)(\(\s*\d[\d,]*\.\d{1,4}\s*\)|\d[\d,]*\.\d{1,4}|-\s*(?=\s|$)|(?<=\s)\d{1,3}(?:,\d{2,3})+(?=\s|$))"
)


def _parse_amt_token(tok: str) -> Optional[float]:
    t = tok.strip()
    if t in ("-", "–", "—"):
        return 0.0
    neg = False
    if t.startswith("(") and t.endswith(")"):
        neg = True
        t = t[1:-1].strip()
    t = t.replace(",", "")
    try:
        v = float(t)
        return -v if neg else v
    except ValueError:
        return None


def _detect_col_anchors(lines: List[str], fy_num: int) -> Tuple[Optional[int], Optional[int], Optional[int], str]:
    """Detect (cy_center_x, py_center_x, third_col_start_or_None, header_line)."""
    yr = 2000 + fy_num
    prev_yr = yr - 1
    cy_pats = [rf"{prev_yr}\s*-\s*{yr}", rf"{prev_yr}\s*-\s*{str(yr)[-2:]}", rf"March\s*[-\s]*(?:31,?)?\s*[-\s]*{yr}", rf"Mar\s*[-\s]*{yr}"]
    py_pats = [rf"{prev_yr-1}\s*-\s*{prev_yr}", rf"{prev_yr-1}\s*-\s*{str(prev_yr)[-2:]}", rf"March\s*[-\s]*(?:31,?)?\s*[-\s]*{prev_yr}", rf"Mar\s*[-\s]*{prev_yr}"]
    third_pats = [rf"01\.04\.2015", rf"March\s*[-\s]*(?:31,?)?\s*[-\s]*{prev_yr-1}", rf"Mar\s*[-\s]*{prev_yr-1}"]
    for l in lines[:35]:
        cy_m = next((m for p in cy_pats for m in [re.search(p, l, re.I)] if m), None)
        py_m = next((m for p in py_pats for m in [re.search(p, l, re.I)] if m), None)
        if cy_m and py_m and py_m.start() > cy_m.start():
            c3_m = next((m for p in third_pats for m in [re.search(p, l, re.I)] if m and m.start() > py_m.end()), None)
            third_cut = (py_m.end() + c3_m.start()) // 2 + 2 if c3_m else None
            return (cy_m.start() + cy_m.end()) // 2, (py_m.start() + py_m.end()) // 2, third_cut, l
    return None, None, None, ""


_BANNER_LINE_RE = re.compile(
    r"^(?:\d{1,3}\s+Indian\s+Oil|Indian\s*Oil\s*Corporation|High\s+O\s*C\s*T\s*A\s*N\s*E|"
    r"Extraordinary\s+Performance|Pos\s*i\s*t\s*ive|SPRINT\s+ahead|To\s*w\s*a\s*rds|"
    r"Energising\s+India|Tiding\s+over|Integrated\s+Annual|6\dth\s+Annual|2nd\s+Integrated|"
    r"3rd\s+Integrated|04-94|C\s*o\s*rpo\s*rate|Financial\s+S\s*t\s*a\s*t|Statutory\s+Re|"
    r"STANDALONE\s+FINANCIAL|CONSOLIDATED\s+FINANCIAL|BALANCE\s+SHEET\s+AS|"
    r"STATEMENT\s+OF\s+PROFIT|STATEMENT\s+OF\s+CASH|\([`J₹]\s*in\s*crore\)|Particulars\s+Note|"
    r"\d{1,3}\s+Inte\s*grate\s*d\s+Annual)",
    re.I,
)


def extract_block_rows(block_txt: str, fy_num: int) -> List[Dict[str, Any]]:
    lines = block_txt.splitlines()
    cy_x, py_x, third_cut, _ = _detect_col_anchors(lines, fy_num)
    if cy_x is None or py_x is None:
        return []

    gap = max(12, py_x - cy_x)
    parsed_lines: List[Tuple[str, List[Tuple[int, int, str, Optional[float]]], str]] = []
    for l_idx, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        low = s.lower()
        if any(
            k in low
            for k in [
                "for and on behalf of board",
                "as per our attached report",
                "place : new delhi",
                "place: new delhi",
                "statement of cash flows is prepared",
                "reconciliation of cash",
                "significant accounting policies",
                "material accounting policies",
            ]
        ):
            break
        if _BANNER_LINE_RE.match(s) or (l_idx < 8 and ("annual report" in low or "indianoil" in low.replace(" ", ""))):
            continue
        if re.fullmatch(r"\d{1,3}", s):
            continue

        matches = []
        for m in AMT_RE.finditer(line):
            tok = m.group(1)
            val = _parse_amt_token(tok)
            if val is not None:
                matches.append((m.start(), m.end(), tok, val))
        label_end = matches[0][0] if matches else len(line)
        lbl_raw = line[:label_end].rstrip()
        lbl_raw = re.sub(r"\s+\d{1,2}(?:\.\d)?\s*$", "", lbl_raw).strip()
        lbl_clean = re.sub(r"\s+", " ", lbl_raw).strip()
        parsed_lines.append((lbl_clean, matches, line))

    # Calibrate rightmost outer column edge using p90 of usable rightmost tokens!
    # Crucially, only filter out third_cut if it's a 3-date-column statement (FY17 Ind AS transition BS).
    right_ends: List[int] = []
    for lbl, matches, _ in parsed_lines:
        if lbl and re.search(r"20\d\d|march|particulars|year ended", lbl, re.I):
            continue
        usable = [m for m in matches if third_cut is None or m[0] < third_cut]
        if len(usable) >= 2 and usable[-1][1] >= py_x - 4:
            right_ends.append(usable[-1][1])
    if right_ends:
        sr = sorted(right_ends)
        py_outer_end = sr[int(0.85 * (len(sr) - 1))]
    else:
        py_outer_end = py_x + 6
    cy_outer_end = py_outer_end - gap
    # Midpoint strictly between outer CY column and outer PY column
    mid_x = (cy_outer_end + py_outer_end) // 2 + 1

    rows: List[Dict[str, Any]] = []
    for lbl, matches, raw_line in parsed_lines:
        if re.match(r"^[\(\[]\s*includes", lbl, re.I) or "relating to prior years" in lbl.lower():
            continue
        usable = [m for m in matches if third_cut is None or m[0] < third_cut]
        cy_val: Optional[float] = None
        py_val: Optional[float] = None

        if len(usable) == 1:
            s_pos, e_pos, _, val = usable[0]
            # Single token: compare with mid_x ONLY if header gap is normal, otherwise check closer column
            if e_pos >= mid_x + 2:
                py_val = val
            else:
                cy_val = val
        elif len(usable) >= 2:
            # In a 2-column statement (once 3rd transition column is excluded), rightmost token in PY zone vs left of it in CY zone
            # Wait: what if there are 2 inner adjustment tokens in CF? Notice if BOTH tokens are far left (< py_outer_end - gap + 3 AND right token < mid_x),
            # left is still cy and right is py (inner CF adjustments [cy_adj, py_adj]!).
            right_m = usable[-1]
            if right_m[1] >= mid_x - 2:
                py_val = right_m[3]
                rem = [m for m in usable[:-1]]
                if rem:
                    # Pick token closest to cy_outer_end (so if both inner + CY total exist, CY total wins!)
                    cy_best = min(rem, key=lambda m: abs(m[1] - cy_outer_end))
                    cy_val = cy_best[3]
            elif len(usable) == 2:
                # Both tokens in left/inner zone (e.g. FY17/18/19 Cash Flow adjustment pairs [cy_adj, py_adj])
                cy_val = usable[0][3]
                py_val = usable[1][3]
            else:
                cy_best = min(usable, key=lambda m: abs(m[1] - cy_outer_end))
                cy_val = cy_best[3]

        rows.append({"label": lbl, "cy": cy_val, "py": py_val, "raw_line": raw_line.rstrip()})
    return rows


def load_pages(fy: str) -> List[str]:
    spec = AR_SPECS[fy]
    raw = (TEXT_DIR / spec["file"]).read_text(errors="replace")
    pgs = raw.split("\x0c")
    if spec["shifted_1819"]:
        pgs = [decode_fy19_text(p) for p in pgs]
    return pgs


_SECTION_HDR_RE = re.compile(
    r"^(?:assets|non[- ]?current\s+assets|current\s+assets|equity\s+and\s+liabilities|"
    r"equity|liabilities|non[- ]?current\s+liabilities|current\s+liabilities|"
    r"iv\.?\s*expenses|expenses|a\.?\s*cash\s+flow|b\.?\s*cash\s+flow|c\.?\s*cash\s+flow|"
    r"financial\s+assets|financial\s+liabilities|tax\s+expense|other\s+comprehensive\s+income)$",
    re.I,
)


def get_statement_rows(fy: str, stmt_key: str) -> List[Dict[str, Any]]:
    spec = AR_SPECS[fy]
    fy_num = int(fy[2:])
    pgs = load_pages(fy)
    flat: List[Dict[str, Any]] = []
    for pno in spec[stmt_key]:
        blocks = split_2up_blocks(pgs[pno - 1]) if spec["two_up"] else [pgs[pno - 1]]
        for b_idx, blk in enumerate(blocks):
            brows = extract_block_rows(blk, fy_num)
            for r in brows:
                r["page"] = pno
                r["half"] = b_idx
                lbl = r["label"]
                cy, py = r["cy"], r["py"]
                if (cy is not None or py is not None) and not lbl and flat:
                    if re.search(r"intangible|amorti|depreciation", flat[-1]["label"], re.I):
                        r["label"] = "Depreciation, Amortisation and Impairment Total"
                    elif re.search(r"trade\s+payables|micro\s+and\s+small|other\s+than\s+micro|creditors", flat[-1]["label"], re.I):
                        r["label"] = "Trade Payables Total"
                    elif flat[-1]["cy"] is None and flat[-1]["py"] is None and not _SECTION_HDR_RE.match(flat[-1]["label"].strip()):
                        flat[-1]["cy"] = cy
                        flat[-1]["py"] = py
                        flat[-1]["page"] = pno
                        continue
                    else:
                        r["label"] = f"__SUBTOTAL_AFTER__ {flat[-1]['label']}"
                elif flat and flat[-1]["cy"] is None and flat[-1]["py"] is None and lbl and (cy is not None or py is not None):
                    if (
                        not _SECTION_HDR_RE.match(flat[-1]["label"].strip())
                        and not re.match(r"^(?:[a-g]|[ivx]+)\)\s+", lbl, re.I)
                        and (
                            lbl[0].islower()
                            or re.match(r"^(and |in |of |for |from |to |process|assets|liabilities|receivables|equivalents|disposal|sale|tax|year|other|associates|joint)", lbl, re.I)
                            or re.search(r"(stock[- ]in|recogni|classified|joint ventures|associates|development|other than|work[- ]in|equity method|accounted for)$", flat[-1]["label"], re.I)
                        )
                    ):
                        flat[-1]["label"] = (flat[-1]["label"] + " " + lbl).strip()
                        flat[-1]["cy"] = cy
                        flat[-1]["py"] = py
                        flat[-1]["page"] = pno
                        continue
                elif flat and (flat[-1]["cy"] is not None or flat[-1]["py"] is not None) and cy is None and py is None and lbl:
                    if (
                        lbl[0].islower()
                        or re.match(r"^(in process|of financial|and work|at amortised|classified as|recognised|profit or loss|\(|&|relating to|before tax)", lbl, re.I)
                    ):
                        flat[-1]["label"] = (flat[-1]["label"] + " " + lbl).strip()
                        continue
                flat.append(r)
    return flat


def _find_rows(
    rows: List[Dict[str, Any]],
    patterns: List[str],
    *,
    after: Optional[str] = None,
    before: Optional[str] = None,
    exclude: Optional[str] = None,
    require_num: bool = True,
) -> List[Dict[str, Any]]:
    started = after is None
    hits: List[Dict[str, Any]] = []
    for r in rows:
        lbl = re.sub(r"\s+", " ", r["label"]).strip()
        if not started and after and re.search(after, lbl, re.I):
            started = True
            continue
        if started and before and re.search(before, lbl, re.I):
            break
        if not started:
            continue
        if exclude and re.search(exclude, lbl, re.I):
            continue
        if require_num and r["cy"] is None and r["py"] is None:
            continue
        if any(re.search(p, lbl, re.I) for p in patterns):
            hits.append(r)
    return hits


def _val(r: Optional[Dict[str, Any]], col: str) -> Optional[float]:
    if not r:
        return None
    return r.get(col)


def parse_pl(rows: List[Dict[str, Any]], col: str, is_consol: bool = False) -> Dict[str, Any]:
    def pick(pats, **kw):
        hs = _find_rows(rows, pats, **kw)
        return hs[0] if hs else None

    rev = pick([r"Revenue From Operations"])
    oth_inc = pick([r"Other Income"])
    tot_inc = pick([r"Total Income"])
    mat = pick([r"Cost of Material(?:s)? Consumed"])
    # Excise Duty in Expenses (careful: in FY20 P&L FY20 line was `77,048.34`? Wait no: in FY20 p85 `[Includes ₹ ... Excise Duty]` came RIGHT AFTER `80,693.19`? Let's match exact `Excise Duty` line and NOT `__SUBTOTAL_AFTER__` unless Excise Duty had blank number on label line!)
    excise = pick([r"^Excise Duty$"])
    if excise is None or _val(excise, col) is None:
        excise = pick([r"Excise Duty"], after=r"Expenses")
    purch = pick([r"Purchases of Stock[- ]in[- ]Trade"])
    chg_inv = pick([r"Changes in Inventories"])
    emp = pick([r"Employee Benefits Expense"])
    fin = pick([r"Finance Costs"])
    dda = pick(
        [r"Depreciation.*Total$", r"Depreciation.*Amorti[sz]ation.*Impairment$", r"Depreciation and Amorti[sz]ation"],
        exclude=r"Tangible Assets|Property,?\s*Plant",
    )
    if dda is None or _val(dda, col) is None:
        for i, r in enumerate(rows):
            if re.search(r"b[\). ]+Intangible Assets|Depreciation.*Amorti", r["label"], re.I):
                for j in range(i, min(i + 4, len(rows))):
                    cand = rows[j]
                    v = cand.get(col)
                    if v is not None and abs(float(v)) > 2000 and not re.search(r"Finance Costs|Employee|Other Expenses|Purchases|Impairment Loss.*Financial", cand["label"], re.I):
                        dda = cand
                        break
                if dda is not None and _val(dda, col) is not None:
                    break
    imp_fin = pick([r"Impairment Loss.*Financial Assets"], before=r"Total Expenses")
    derecog = pick([r"Net Loss on de[- ]?recognition"], before=r"Total Expenses")
    oth_exp = pick([r"\bOther Expenses\b"], after=r"Expenses", before=r"Total Expenses", exclude=r"Depreciation|Employee")
    tot_exp = pick([r"Total Expenses"])
    share_jv = pick([r"Share of profit.*(?:associates|joint ventures)"], after=r"Total Expenses") if is_consol else None
    pbt_pre = pick([r"Profit\s*(?:/?\s*\(?Loss\)?)?\s*before.*Tax"], after=r"Total Expenses", exclude=r"Share of Profit")
    exc_item = pick([r"Exceptional Items"], after=r"Total Expenses", before=r"Tax Expense", exclude=r"before Exceptional")
    pbt = pick([r"Profit\s*(?:/?\s*\(?Loss\)?)?\s*before Tax"], after=r"Total Expenses", exclude=r"before Exceptional|before Share")
    if pbt is None or _val(pbt, col) is None:
        pbt = pick([r"V\.?\s*Profit\s*before\s*Tax", r"Profit\s*(?:/?\s*\(?Loss\)?)?\s*before Exceptional Items and Tax"], after=r"Total Expenses")
    if pbt_pre is None or _val(pbt_pre, col) is None:
        pbt_pre = pbt
    tax_curr = pick([r"^Current Tax", r"Current tax"], after=r"Tax Expense", before=r"Profit.*for\s*the\s*(?:Year|Period)")
    tax_def = pick([r"^Deferred Tax", r"Deferred tax"], after=r"Tax Expense", before=r"Profit.*for\s*the\s*(?:Year|Period)")
    pat = pick([r"Profit\s*(?:/?\s*\(?Loss\)?)?\s*for\s*the\s*(?:Year|Period)"], after=r"Tax Expense", exclude=r"attributable|Total Comprehensive")
    tci = pick([r"Total Comprehensive Income"], exclude=r"attributable")
    pat_owners = pick([r"(?:Equityholders|Owners) of the Parent"], after=r"attributable to") if is_consol else None
    pat_nci = pick([r"Non[- ]?Controlling Interest"], after=r"attributable to") if is_consol else None
    eps_b = pick([r"Basic"], after=r"Earning(?:s)? per Equity Share")
    eps_d = pick([r"Diluted"], after=r"Earning(?:s)? per Equity Share")

    # Note on FY20 P&L Excise Duty: look carefully if Excise Duty line was split into two lines where the 1st line is inner excise (`[Includes ...]`)!
    # Check if there is `__SUBTOTAL_AFTER__ Excise Duty` on the next line AND `sum(expenses) == total_expenses` distinguishes them!
    exc_val = _val(excise, col)
    sub_exc = pick([r"__SUBTOTAL_AFTER__.*Excise Duty"], after=r"Expenses")
    if sub_exc and _val(sub_exc, col) is not None and _val(tot_exp, col) is not None:
        base_sum = sum(
            float(_val(x, col) or 0.0)
            for x in (mat, purch, chg_inv, emp, fin, dda, imp_fin, derecog, oth_exp)
        )
        if abs((base_sum + float(_val(sub_exc, col))) - float(_val(tot_exp, col))) < abs((base_sum + float(exc_val or 0.0)) - float(_val(tot_exp, col))):
            exc_val = _val(sub_exc, col)

    d: Dict[str, Any] = {
        "revenue_from_operations": _val(rev, col),
        "other_income": _val(oth_inc, col),
        "total_income": _val(tot_inc, col),
        "cost_of_materials_consumed": _val(mat, col),
        "excise_duty": exc_val,
        "purchases_of_stock_in_trade": _val(purch, col),
        "changes_in_inventories": _val(chg_inv, col),
        "employee_benefits_expense": _val(emp, col),
        "finance_costs": _val(fin, col),
        "dda": _val(dda, col),
        "impairment_fin_assets": _val(imp_fin, col) if imp_fin and _val(imp_fin, col) is not None else 0.0,
        "net_loss_derecognition": _val(derecog, col) if derecog and _val(derecog, col) is not None else 0.0,
        "other_expenses": _val(oth_exp, col),
        "total_expenses": _val(tot_exp, col),
        "pbt_before_exceptional": _val(pbt_pre, col),
        "exceptional_items": _val(exc_item, col) if exc_item and _val(exc_item, col) is not None else 0.0,
        "pbt": _val(pbt, col),
        "current_tax": _val(tax_curr, col),
        "deferred_tax": _val(tax_def, col),
        "pat": _val(pat, col),
        "total_comprehensive_income": _val(tci, col),
        "eps_basic_printed": _val(eps_b, col),
        "eps_diluted_printed": _val(eps_d, col),
        "pages": sorted({r["page"] for r in rows if "page" in r}),
    }
    if is_consol:
        d["share_of_jv_associates"] = _val(share_jv, col) if share_jv else 0.0
        d["pat_owners"] = _val(pat_owners, col)
        d["pat_nci"] = _val(pat_nci, col)
    return d


def parse_bs(rows: List[Dict[str, Any]], col: str, is_consol: bool = False) -> Dict[str, Any]:
    def pick(pats, **kw):
        hs = _find_rows(rows, pats, **kw)
        return hs[0] if hs else None

    sub_assets = _find_rows(rows, [r"__SUBTOTAL_AFTER__", r"Total Non[- ]?current Assets"], after=r"Non[- ]?current Assets", before=r"^Current Assets")
    nca_tot = sub_assets[-1] if sub_assets else None
    ca_sub_all = _find_rows(rows, [r"__SUBTOTAL_AFTER__", r"Total Current Assets"], after=r"^Current Assets", before=r"EQUITY AND LIABILITIES|^TOTAL")
    hfs = pick([r"Assets Held for (?:Sale|Disposal)"], after=r"^Current Assets", before=r"EQUITY AND LIABILITIES")
    tot_assets = pick([r"^TOTAL ASSETS", r"^TOTAL$"], after=r"^Current Assets", before=r"EQUITY AND LIABILITIES")

    ca_pre_hfs = ca_sub_all[0] if ca_sub_all else None
    ca_tot = ca_sub_all[-1] if ca_sub_all else None

    # Notice in Consolidated BS (FY17..FY26), Equity has: Equity Share Capital, Other Equity, [Equity Owners subtotal], NCI, Total Equity!
    eq_subs = _find_rows(rows, [r"__SUBTOTAL_AFTER__", r"Total Equity", r"(?:Equityholders|Owners) of the Parent"], after=r"^EQUITY$", before=r"^LIABILITIES|^Non[- ]?current Liabilities")
    tot_eq = eq_subs[-1] if eq_subs else None
    # Note: for FY17..FY18 Consol BS, check if `Total Equity` comes after `Non-Controlling Interest`:
    if is_consol and tot_eq is None:
        eq_subs2 = _find_rows(rows, [r"__SUBTOTAL_AFTER__", r"Total Equity"], after=r"^EQUITY$", before=r"^Non[- ]?current Liabilities")
        tot_eq = eq_subs2[-1] if eq_subs2 else None

    ncl_subs = _find_rows(rows, [r"__SUBTOTAL_AFTER__", r"Total Non[- ]?current Liabilities"], after=r"^LIABILITIES$", before=r"^Current Liabilities")
    tot_ncl = ncl_subs[-1] if ncl_subs else None
    cl_subs = _find_rows(rows, [r"__SUBTOTAL_AFTER__", r"Total Current Liabilities", r"^TOTAL$"], after=r"^Current Liabilities", before=r"TOTAL EQUITY AND LIABILITIES")
    tot_eq_liab = pick([r"TOTAL EQUITY AND LIABILITIES"], after=r"^Current Liabilities")
    if tot_eq_liab is None:
        tot_rows_end = _find_rows(rows, [r"__SUBTOTAL_AFTER__", r"^TOTAL"], after=r"^Current Liabilities")
        if len(tot_rows_end) >= 2:
            tot_cl = tot_rows_end[-2]
            tot_eq_liab = tot_rows_end[-1]
        elif tot_rows_end:
            tot_eq_liab = tot_rows_end[-1]
            tot_cl = cl_subs[-1] if cl_subs else None
    else:
        tot_cl = cl_subs[-1] if cl_subs else None

    ppe = pick([r"Property,?\s*Plant and Equipment"], after=r"Non[- ]?current Assets", before=r"^Current Assets")
    cwip = pick([r"Capital Work[- ]in[- ]Progress"], after=r"Non[- ]?current Assets", before=r"^Current Assets")
    inv_prop = pick([r"Investment Property"], after=r"Non[- ]?current Assets", before=r"^Current Assets")
    rou = pick([r"Right[- ]of[- ]use"], after=r"Non[- ]?current Assets", before=r"^Current Assets")
    goodwill = pick([r"Goodwill"], after=r"Non[- ]?current Assets", before=r"^Current Assets")
    intang = pick([r"Intangible Assets$"], after=r"Non[- ]?current Assets", before=r"Under Development|^Current Assets")
    intang_dev = pick([r"Intangible Assets Under Development"], after=r"Non[- ]?current Assets", before=r"^Current Assets")
    inv_sub = pick([r"Subsidiaries.*Joint Ventures|Joint Ventures.*Associates"], after=r"Non[- ]?current Assets", before=r"^Current Assets")
    inv_oth_nc = pick([r"Other Investments"], after=r"Non[- ]?current Assets", before=r"^Current Assets")

    inv_cur_tot = pick([r"Inventories"], after=r"^Current Assets", before=r"EQUITY AND LIABILITIES")
    rec = pick([r"Trade Receivables"], after=r"^Current Assets", before=r"EQUITY AND LIABILITIES")
    cash = pick([r"Cash and Cash Equivalents"], after=r"^Current Assets", before=r"EQUITY AND LIABILITIES")
    bank_oth = pick([r"Bank Balances other than"], after=r"^Current Assets", before=r"EQUITY AND LIABILITIES")
    inv_curr = pick([r"Investments"], after=r"^Current Assets", before=r"Trade Receivables")

    eq_cap = pick([r"Equity Share Capital"], after=r"^EQUITY$", before=r"^LIABILITIES")
    oth_eq = pick([r"Other Equity"], after=r"^EQUITY$", before=r"^LIABILITIES")
    nci_eq = pick([r"Non[- ]?Controlling Interest"], after=r"^EQUITY$", before=r"^LIABILITIES") if is_consol else None
    eq_owners = eq_subs[0] if (is_consol and eq_subs and len(eq_subs) >= 2) else None

    lt_borr = pick([r"Borrowings"], after=r"^LIABILITIES$", before=r"^Current Liabilities")
    lt_lease = pick([r"Lease Liabilities"], after=r"^LIABILITIES$", before=r"^Current Liabilities")
    dtl = pick([r"Deferred Tax Liabilities"], after=r"^LIABILITIES$", before=r"^Current Liabilities")

    st_borr = pick([r"Borrowings"], after=r"^Current Liabilities")
    st_lease = pick([r"Lease Liabilities"], after=r"^Current Liabilities")
    tp_msme = pick([r"Micro and Small"], after=r"^Current Liabilities", before=r"Other Current Liabilities", exclude=r"creditors other than|Lease Liabilities|Borrowings")
    tp_oth = pick([r"creditors other than"], after=r"^Current Liabilities", before=r"Other Current Liabilities", exclude=r"Lease Liabilities|Borrowings")
    if tp_msme and tp_oth and _val(tp_msme, col) is not None and _val(tp_oth, col) is not None:
        tp_val = round(float(_val(tp_msme, col)) + float(_val(tp_oth, col)), 2)
    else:
        tp_tot = pick([r"Trade Payables Total$"], after=r"^Current Liabilities", exclude=r"Lease Liabilities|Borrowings")
        if tp_tot is not None and _val(tp_tot, col) is not None:
            tp_val = _val(tp_tot, col)
        else:
            tp_row = pick([r"Trade Payables"], after=r"^Current Liabilities", before=r"Other Current Liabilities", exclude=r"Lease Liabilities|Borrowings")
            tp_val = _val(tp_row, col)

    hfs_liab = pick([r"Liabilities.*Held for (?:Sale|Disposal)"], after=r"^Current Liabilities")

    return {
        "ppe": _val(ppe, col),
        "cwip": _val(cwip, col),
        "investment_property": _val(inv_prop, col) if inv_prop else 0.0,
        "rou_assets": _val(rou, col) if rou else 0.0,
        "goodwill": _val(goodwill, col) if goodwill else 0.0,
        "intangible_assets": _val(intang, col),
        "intangible_under_dev": _val(intang_dev, col),
        "investments_sub_jv": _val(inv_sub, col) if inv_sub else None,
        "investments_other_nc": _val(inv_oth_nc, col) if inv_oth_nc else None,
        "total_non_current_assets": _val(nca_tot, col),
        "inventories": _val(inv_cur_tot, col),
        "investments_current": _val(inv_curr, col),
        "trade_receivables": _val(rec, col),
        "cash_and_cash_equivalents": _val(cash, col),
        "other_bank_balances": _val(bank_oth, col),
        "subtotal_current_assets_pre_hfs": _val(ca_pre_hfs, col),
        "assets_held_for_sale": _val(hfs, col) if hfs else 0.0,
        "total_current_assets": _val(ca_tot, col),
        "total_assets": _val(tot_assets, col),
        "equity_share_capital": _val(eq_cap, col),
        "other_equity": _val(oth_eq, col),
        "equity_owners": _val(eq_owners, col) if is_consol else None,
        "nci_equity": _val(nci_eq, col) if nci_eq else None,
        "total_equity": _val(tot_eq, col),
        "lt_borrowings": _val(lt_borr, col),
        "lt_lease_liabilities": _val(lt_lease, col) if lt_lease else 0.0,
        "dtl_net": _val(dtl, col),
        "total_non_current_liabilities": _val(tot_ncl, col),
        "st_borrowings": _val(st_borr, col),
        "st_lease_liabilities": _val(st_lease, col) if st_lease else 0.0,
        "trade_payables": tp_val,
        "liabilities_held_for_sale": _val(hfs_liab, col) if hfs_liab else 0.0,
        "total_current_liabilities": _val(tot_cl, col),
        "total_equity_and_liabilities": _val(tot_eq_liab, col),
        "pages": sorted({r["page"] for r in rows if "page" in r}),
    }


def parse_cf(rows: List[Dict[str, Any]], col: str) -> Dict[str, Any]:
    def pick(pats, **kw):
        hs = _find_rows(rows, pats, **kw)
        return hs[0] if hs else None

    cf_pbt = pick([r"Profit\s*/?\s*\(?Loss\)?\s*before Tax"], before=r"Investing Activities")
    op_wc = pick([r"Operating Profit before Working Capital"], before=r"Investing Activities")
    wc_chg = pick([r"^Change in Working Capital"], before=r"Investing Activities")
    cash_gen = pick([r"Cash Generated From Operations"], before=r"Investing Activities")
    tax_paid = pick([r"(?:Income )?Tax(?:es)? paid"], before=r"Investing Activities")
    ocf = pick([r"Net Cash (?:Generated|Flow).*Operating Activities"], before=r"Investing Activities")

    capex_ppe = pick([r"Purchase of Property,?\s*Plant|Additions to Property,?\s*Plant"], after=r"Investing Activities", before=r"Financing Activities")
    capex_cwip = pick([r"Expenditure on Construction Work"], after=r"Investing Activities", before=r"Financing Activities")
    icf = pick([r"Net Cash (?:Generated|Used|Flow).*Investing Activities"], after=r"Investing Activities", before=r"Financing Activities")

    lease_paid = pick([r"Payment(?:s)? of Lease Liabilities"], after=r"Financing Activities")
    int_paid = pick([r"Interest paid"], after=r"Financing Activities")
    div_paid = pick([r"Dividend.*paid"], after=r"Financing Activities")
    cff = pick([r"Net Cash (?:Generated|Used|Flow).*Financing Activities"], after=r"Financing Activities")

    net_chg = pick([r"Net Change in Cash"], after=r"Financing Activities")
    e_open = pick([r"Cash & Cash Equivalents as at (?:the )?beginning|Opening"], after=r"Financing Activities")
    e_close = pick([r"Cash & Cash Equivalents as at (?:the )?end|Closing"], after=r"Financing Activities")

    tot_capex = None
    if _val(capex_ppe, col) is not None:
        tot_capex = round(abs(float(_val(capex_ppe, col) or 0)) + abs(float(_val(capex_cwip, col) or 0)), 2)

    return {
        "cf_pbt": _val(cf_pbt, col),
        "cf_op_before_wc": _val(op_wc, col),
        "cf_wc_changes": _val(wc_chg, col),
        "cf_cash_gen_ops": _val(cash_gen, col),
        "cf_tax_paid": _val(tax_paid, col),
        "ocf": _val(ocf, col),
        "cf_capex_ppe": _val(capex_ppe, col),
        "cf_capex_cwip": _val(capex_cwip, col),
        "cf_total_capex": tot_capex,
        "icf": _val(icf, col),
        "cf_lease_paid": _val(lease_paid, col) if lease_paid else 0.0,
        "cf_interest_paid": _val(int_paid, col),
        "cf_dividend_paid": _val(div_paid, col),
        "cff": _val(cff, col),
        "cf_net_change_cce": _val(net_chg, col),
        "cf_open_cce": _val(e_open, col),
        "cf_close_cce": _val(e_close, col),
        "pages": sorted({r["page"] for r in rows if "page" in r}),
    }


def extract_notes_and_segments(fy: str) -> Dict[str, Any]:
    """Extract Note 31/32 EPS shares, Note 44 R&D, Note 45 CSR, Note 36 Capital Commitments & Contingencies, and Note 38 Segment Info."""
    spec = AR_SPECS[fy]
    pgs = load_pages(fy)

    def get_note_text(key: str) -> str:
        chunks = []
        for pno in spec[key]:
            txt = pgs[pno - 1]
            if spec["two_up"]:
                chunks.extend(split_2up_blocks(txt))
            else:
                chunks.append(txt)
        return "\n".join(chunks)

    # 1. EPS Note: Weighted avg shares (Indian comma format e.g. 13,77,15,60,699 or 9,47,86,87,642) & printed EPS
    eps_txt = get_note_text("eps")
    wavg_shares_cr: Optional[float] = None
    m_sh = re.search(
        r"Weighted Average number of Equity Shares.*?(?:Basic|EPS).*?([\d,]{8,16})",
        eps_txt,
        re.I | re.S,
    )
    if m_sh:
        raw_sh = float(m_sh.group(1).replace(",", ""))
        wavg_shares_cr = round(raw_sh / 1e7, 4)

    # 2. R&D Note 44
    rnd_txt = get_note_text("rnd")
    rnd_cap = rnd_rec = rnd_tot = None
    m_rnd = re.search(r"TOTAL RESEARCH EXPENSES.*?Capital Expenditure\s+([\d,]+\.\d{2}).*?Recurring Expenditure\s+([\d,]+\.\d{2}).*?Total\s+([\d,]+\.\d{2})", rnd_txt, re.I | re.S)
    if m_rnd:
        rnd_cap = float(m_rnd.group(1).replace(",", ""))
        rnd_rec = float(m_rnd.group(2).replace(",", ""))
        rnd_tot = float(m_rnd.group(3).replace(",", ""))
    else:
        m_rnd2 = re.search(r"Research and Development Expenses of\s*[`₹HJ]?\s*([\d,]+\.\d{2})\s*crore.*?capital(?:ized| expenditure).*?[`₹HJ]?\s*([\d,]+\.\d{2})\s*crore", rnd_txt, re.I | re.S)
        if m_rnd2:
            rnd_cap = float(m_rnd2.group(1).replace(",", ""))
            rnd_rec = float(m_rnd2.group(2).replace(",", ""))
            rnd_tot = round(rnd_cap + rnd_rec, 2)

    # 3. CSR Note 45/46
    csr_txt = get_note_text("csr")
    csr_req = csr_spent = None
    m_csr_req = re.search(r"Gross amount required to be spent.*?([\d,]+\.\d{2})", csr_txt, re.I | re.S)
    if m_csr_req:
        csr_req = float(m_csr_req.group(1).replace(",", ""))
    m_csr_sp = re.search(r"(?:Amount spent during the year|Total amount spent for the financial year).*?([\d,]+\.\d{2})", csr_txt, re.I | re.S)
    if m_csr_sp:
        csr_spent = float(m_csr_sp.group(1).replace(",", ""))

    # 4. Capital Commitments Note 36 A
    cc_txt = get_note_text("comm_cont")
    cap_comm = None
    m_cc = re.search(r"Estimated amount of contracts remaining to be executed on Capital Account.*?([\d,]+\.\d{2})", cc_txt, re.I | re.S)
    if m_cc:
        cap_comm = float(m_cc.group(1).replace(",", ""))

    # 5. Note 38 Segment Information (Petroleum Products, Petrochemicals, Gas Segment, Other Business, Total)
    seg_txt = get_note_text("seg")
    seg_data: Dict[str, Any] = {"pages": spec["seg"], "raw_excerpt_found": "SEGMENT INFORMATION" in seg_txt.upper()}
    # Detect whether Gas Segment is a standalone column (FY25, FY26) vs 3-segment earlier years
    lines = seg_txt.splitlines()
    has_gas = int(fy[2:]) >= 25 and any("gas" in l.lower() and "segment" in l.lower() for l in lines)
    # Extract CY block rows of External Revenue, Inter-segment, Total Revenue, Segment Results
    for tag, pat in [
        ("external_revenue", r"^External Revenue"),
        ("inter_segment_revenue", r"^Inter[- ]?segment\s*(?:Revenue)?"),
        ("total_revenue", r"^Total Revenue"),
        ("segment_results_ex_fx", r"^Segment Results\s*(?:excluding|before)"),
        ("segment_results", r"^Segment\s*Results(?!\s*(?:excluding|before))\b"),
        ("segment_assets", r"^Segment Assets"),
        ("segment_liabilities", r"^Segment Liabilities"),
        ("segment_capex", r"^Capital Expenditure"),
    ]:
        for idx, l in enumerate(lines):
            if re.search(pat, l.strip(), re.I):
                nums = [float(x.replace(",", "").replace("(", "-").replace(")", "")) if x.strip() not in ("-", "–") else 0.0 for x in re.findall(r"\(\s*\d[\d,]*\.\d{2}\s*\)|\d[\d,]*\.\d{2}|(?<=\s)-(?=\s|$)", l)]
                if len(nums) >= 4:
                    # First half of row numbers corresponds to CY (4-5 cols in CY + 4-5 cols in PY!)
                    half = len(nums) // 2 if len(nums) >= 8 else len(nums)
                    seg_data[tag] = nums[:half]
                    break
    seg_data["has_gas_segment_col"] = has_gas

    return {
        "weighted_avg_shares_cr": wavg_shares_cr,
        "rnd_capex_cr": rnd_cap,
        "rnd_recurring_cr": rnd_rec,
        "rnd_total_cr": rnd_tot,
        "csr_required_cr": csr_req,
        "csr_spent_cr": csr_spent,
        "capital_commitments_cr": cap_comm,
        "segment": seg_data,
        "pages": {k: spec[k] for k in ("seg", "eps", "inv", "comm_cont", "rnd", "csr")},
    }


def main() -> None:
    result: Dict[str, Any] = {"years": {}}
    for i, fy in enumerate(FYS):
        s_bs_r = get_statement_rows(fy, "s_bs")
        s_pl_r = get_statement_rows(fy, "s_pl")
        s_cf_r = get_statement_rows(fy, "s_cf")
        c_bs_r = get_statement_rows(fy, "c_bs")
        c_pl_r = get_statement_rows(fy, "c_pl")
        c_cf_r = get_statement_rows(fy, "c_cf")

        own = {
            "source_doc": AR_SPECS[fy]["file"].replace(".txt", ".pdf"),
            "standalone_bs": parse_bs(s_bs_r, "cy", is_consol=False),
            "standalone_pl": parse_pl(s_pl_r, "cy", is_consol=False),
            "standalone_cf": parse_cf(s_cf_r, "cy"),
            "consolidated_bs": parse_bs(c_bs_r, "cy", is_consol=True),
            "consolidated_pl": parse_pl(c_pl_r, "cy", is_consol=True),
            "consolidated_cf": parse_cf(c_cf_r, "cy"),
            "notes": extract_notes_and_segments(fy),
        }
        comp = None
        if i + 1 < len(FYS):
            next_fy = FYS[i + 1]
            comp = {
                "from_ar": next_fy,
                "source_doc": AR_SPECS[next_fy]["file"].replace(".txt", ".pdf"),
                "standalone_bs": parse_bs(get_statement_rows(next_fy, "s_bs"), "py", is_consol=False),
                "standalone_pl": parse_pl(get_statement_rows(next_fy, "s_pl"), "py", is_consol=False),
                "standalone_cf": parse_cf(get_statement_rows(next_fy, "s_cf"), "py"),
                "consolidated_bs": parse_bs(get_statement_rows(next_fy, "c_bs"), "py", is_consol=True),
                "consolidated_pl": parse_pl(get_statement_rows(next_fy, "c_pl"), "py", is_consol=True),
                "consolidated_cf": parse_cf(get_statement_rows(next_fy, "c_cf"), "py"),
            }
        result["years"][fy] = {"own_vintage": own, "comparative_in_next_ar": comp}

    failures = 0
    print(f"{'FY':4s} | {'RevOp':>10s} | {'Excise':>10s} | {'PAT':>9s} | {'TotAsset':>10s} | {'Equity':>10s} | {'OCF':>9s} | {'ConsolPAT':>9s} | {'Checks'}")
    print("-" * 118)
    for fy in FYS:
        o = result["years"][fy]["own_vintage"]
        pl, bs, cf = o["standalone_pl"], o["standalone_bs"], o["standalone_cf"]
        cpl, cbs, ccf = o["consolidated_pl"], o["consolidated_bs"], o["consolidated_cf"]
        errs = []
        for k in ("revenue_from_operations", "other_income", "total_income", "total_expenses", "pbt", "pat", "dda"):
            if pl[k] is None:
                errs.append(f"PL_NONE:{k}")
        if all(pl[k] is not None for k in ("revenue_from_operations", "other_income", "total_income", "total_expenses", "pbt", "pat")):
            if abs((pl["revenue_from_operations"] + pl["other_income"]) - pl["total_income"]) > 0.05:
                errs.append("PL_TOT_INC")
            if abs((pl["total_income"] - pl["total_expenses"]) - (pl["pbt_before_exceptional"] or pl["pbt"])) > 0.05:
                errs.append("PL_PBT_PRE")
            if abs((pl["pbt"] - (pl["current_tax"] or 0) - (pl["deferred_tax"] or 0)) - pl["pat"]) > 0.05:
                errs.append("PL_TAX")
        for k in ("total_non_current_assets", "total_current_assets", "total_assets", "total_equity", "total_equity_and_liabilities"):
            if bs[k] is None:
                errs.append(f"BS_NONE:{k}")
        if all(bs[k] is not None for k in ("total_non_current_assets", "total_current_assets", "total_assets", "total_equity", "total_equity_and_liabilities")):
            if abs((bs["total_non_current_assets"] + bs["total_current_assets"]) - bs["total_assets"]) > 0.05:
                errs.append("BS_ASSETS_SUM")
            if abs((bs["total_equity"] + (bs["total_non_current_liabilities"] or 0) + (bs["total_current_liabilities"] or 0)) - bs["total_equity_and_liabilities"]) > 0.05:
                errs.append("BS_LIAB_SUM")
            if abs(bs["total_assets"] - bs["total_equity_and_liabilities"]) > 0.05:
                errs.append("BS_BAL")
        for k in ("ocf", "icf", "cff", "cf_net_change_cce", "cf_open_cce", "cf_close_cce"):
            if cf[k] is None:
                errs.append(f"CF_NONE:{k}")
        if all(cf[k] is not None for k in ("ocf", "icf", "cff", "cf_net_change_cce", "cf_open_cce", "cf_close_cce")):
            if abs((cf["ocf"] + cf["icf"] + cf["cff"]) - cf["cf_net_change_cce"]) > 0.25:
                errs.append("CF_SUM")
            if abs((cf["cf_open_cce"] + cf["cf_net_change_cce"]) - cf["cf_close_cce"]) > 0.05:
                errs.append("CF_CCE")
            if bs["cash_and_cash_equivalents"] is not None and abs(cf["cf_close_cce"] - bs["cash_and_cash_equivalents"]) > 0.05:
                errs.append("CF_BS_CASH")
        for ck in ("revenue_from_operations", "pat"):
            if cpl[ck] is None:
                errs.append(f"CPL_NONE:{ck}")
        for ck in ("total_assets", "total_equity"):
            if cbs[ck] is None:
                errs.append(f"CBS_NONE:{ck}")
        if ccf["ocf"] is None:
            errs.append("CCF_NONE:ocf")

        if errs:
            failures += 1
        print(
            f"{fy:4s} | {str(pl['revenue_from_operations']):>10s} | {str(pl['excise_duty']):>10s} | "
            f"{str(pl['pat']):>9s} | {str(bs['total_assets']):>10s} | {str(bs['total_equity']):>10s} | "
            f"{str(cf['ocf']):>9s} | {str(cpl['pat']):>9s} | {'OK' if not errs else '; '.join(errs)}"
        )

    OUT_JSON.write_text(json.dumps(result, indent=2))
    print(f"\nSaved {OUT_JSON} (years with parse/check warnings: {failures})")


if __name__ == "__main__":
    main()
