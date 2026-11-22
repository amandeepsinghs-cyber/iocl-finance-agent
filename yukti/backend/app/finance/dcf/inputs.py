"""SSOT & market-seed input loaders for the DCF valuation engine (SPEC-02, BUG-12).

Loads FY26 WACC from `financial_ssot/out/fact_wacc_annual.parquet` and FY26 NSE close
price from `knowledge/public_sources/market_data/manual/market_prices_seed.csv` (with
fallback to `financial_ssot/out/fact_wacc_input.parquet`) with full provenance lineage.
"""

from __future__ import annotations

import csv
import logging
import math
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger("yukti.dcf.inputs")


class DCFInputMissingError(ValueError):
    """Raised when a required DCF SSOT or market-price input is missing, unverified, or NULL."""

    def __init__(self, missing_input: str, message: Optional[str] = None):
        self.missing_input = missing_input
        super().__init__(message or f"Missing or unverified DCF input: {missing_input}")


def _resolve_asset(rel_path: str) -> Path:
    here = Path(__file__).resolve()
    for depth in (5, 4, 3):
        if len(here.parents) > depth:
            cand = here.parents[depth] / rel_path
            if cand.exists():
                return cand
    return here.parents[min(5, len(here.parents) - 1)] / rel_path


SNAPSHOT_PARQUET = _resolve_asset("financial_ssot/out/fact_snapshot.parquet")
WACC_ANNUAL_PARQUET = _resolve_asset("financial_ssot/out/fact_wacc_annual.parquet")
WACC_INPUT_PARQUET = _resolve_asset("financial_ssot/out/fact_wacc_input.parquet")
MARKET_SEED_CSV = _resolve_asset("knowledge/public_sources/market_data/manual/market_prices_seed.csv")


def _opt_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def load_wacc_annual_rows() -> List[Dict[str, Any]]:
    if not WACC_ANNUAL_PARQUET.exists():
        return []
    df = pd.read_parquet(WACC_ANNUAL_PARQUET)
    return df.to_dict(orient="records")


def load_ssot_snapshot_rows(fy: str = "FY26", scope: str = "standalone") -> List[Dict[str, Any]]:
    if not SNAPSHOT_PARQUET.exists():
        return []
    df = pd.read_parquet(SNAPSHOT_PARQUET)
    mask = (df["fiscal_year"] == fy) & (df["scope"] == scope)
    if "is_latest_vintage" in df.columns:
        mask = mask & (df["is_latest_vintage"] == True)  # noqa: E712
    sub = df[mask]
    return sub.to_dict(orient="records")


def load_fy26_wacc_default(
    wacc_table: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[float, str, Dict[str, Any]]:
    """Return (wacc_pct, source_label, row_metadata) for FY26 from fact_wacc_annual.

    Raises DCFInputMissingError('fact_wacc_annual') when the file/table is missing,
    has no verified/modelled FY26 row, or has NULL WACC / required components.
    """
    using_ssot_file = wacc_table is None or len(wacc_table) == 0
    rows = load_wacc_annual_rows() if using_ssot_file else wacc_table
    if not rows:
        raise DCFInputMissingError("fact_wacc_annual")

    for row in rows:
        if row.get("fiscal_year") == "FY26":
            wacc_val = _opt_float(row.get("wacc_pct"))
            if wacc_val is not None and (
                row.get("verified", False) or row.get("provenance_label") in ("modelled", "verified_ar")
            ):
                val = round(wacc_val, 4)
                meta: Dict[str, Any] = {
                    "fiscal_year": "FY26",
                    "wacc_pct": val,
                    "as_of_date": str(row.get("as_of_date") or ""),
                    "rf_used_pct": _opt_float(row.get("rf_used_pct")),
                    "default_spread_pct": _opt_float(row.get("default_spread_pct")),
                    "erp_total_pct": _opt_float(row.get("erp_total_pct")),
                    "beta_industry_relevered": _opt_float(row.get("beta_industry_relevered")),
                    "ke_pct": _opt_float(row.get("ke_pct")),
                    "kd_pretax_pct": _opt_float(row.get("kd_pretax_pct")),
                    "kd_used_pct": _opt_float(row.get("kd_used_pct")),
                    "tax_rate_pct": _opt_float(row.get("tax_rate_pct")),
                    "weight_equity": _opt_float(row.get("weight_equity")),
                    "weight_debt": _opt_float(row.get("weight_debt")),
                    "wacc_alt_gsec_less_spread_pct": _opt_float(row.get("wacc_alt_gsec_less_spread_pct")),
                    "method_version": str(row.get("method_version") or "wacc-v1"),
                    "object": "hrfin_gold.fact_wacc_annual",
                }
                if using_ssot_file:
                    required_components = (
                        "rf_used_pct",
                        "default_spread_pct",
                        "erp_total_pct",
                        "beta_industry_relevered",
                        "ke_pct",
                        "kd_used_pct",
                        "tax_rate_pct",
                        "weight_equity",
                        "weight_debt",
                    )
                    missing_comp = [k for k in required_components if meta.get(k) is None]
                    if missing_comp:
                        raise DCFInputMissingError(
                            "fact_wacc_annual",
                            f"fact_wacc_annual FY26 row is missing component(s): {', '.join(missing_comp)}",
                        )
                return val, "fact_wacc_annual FY26", meta

    raise DCFInputMissingError("fact_wacc_annual")


def load_fy26_market_price_default() -> Tuple[float, str, Dict[str, Any]]:
    """Return (close_price_inr, source_label, lineage_metadata) for FY26 IOC.NS close.

    Raises DCFInputMissingError when both market_prices_seed.csv and fact_wacc_input.parquet
    are missing or contain no valid FY26 market price.
    """
    if MARKET_SEED_CSV.exists():
        latest_row: Optional[Dict[str, str]] = None
        with open(MARKET_SEED_CSV, "r", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                ticker = (row.get("ticker") or "").strip()
                dt = (row.get("date") or "").strip()
                if ticker in ("IOC.NS", "IOC", "") and dt.startswith("2026-03"):
                    if latest_row is None or dt >= (latest_row.get("date") or ""):
                        latest_row = row
        if latest_row and latest_row.get("close"):
            px_opt = _opt_float(latest_row.get("close"))
            if px_opt is not None and px_opt > 0:
                px = round(px_opt, 2)
                dt = (latest_row.get("date") or "").strip()
                src_url = (latest_row.get("source_url") or "").strip()
                ret_by = (latest_row.get("retrieved_by") or "").strip()
                return (
                    px,
                    f"market_prices_seed.csv (NSE EQ close {dt})",
                    {
                        "ticker": "IOC.NS",
                        "date": dt,
                        "close_inr": px,
                        "source_doc": "market_prices_seed.csv",
                        "source_url": src_url,
                        "retrieved_by": ret_by,
                    },
                )

    if WACC_INPUT_PARQUET.exists():
        df = pd.read_parquet(WACC_INPUT_PARQUET)
        sub = df[df["fiscal_year"] == "FY26"]
        eq_rows = sub[sub["input_code"] == "equity_mv"]
        sh_rows = sub[sub["input_code"] == "shares_outstanding"]
        if not eq_rows.empty and not sh_rows.empty:
            eq_row = eq_rows.iloc[0]
            sh_row = sh_rows.iloc[0]
            eq_mv = _opt_float(eq_row.get("value"))
            shares = _opt_float(sh_row.get("value"))
            if eq_mv is not None and shares is not None and eq_mv > 0 and shares > 0:
                px = round((eq_mv * 1e7) / shares, 2)
                notes = str(eq_row.get("notes") or "")
                m_dt = re.search(r"(\d{4}-\d{2}-\d{2})", notes)
                dt = m_dt.group(1) if m_dt else str(eq_row.get("retrieved_at") or "")[:10]
                return (
                    px,
                    f"market_prices_seed.csv (NSE EQ close {dt})",
                    {
                        "ticker": "IOC.NS",
                        "date": dt,
                        "close_inr": px,
                        "source_doc": str(eq_row.get("source_doc") or "fact_wacc_input.parquet"),
                        "source_url": str(eq_row.get("source_url") or ""),
                        "notes": notes,
                    },
                )

    raise DCFInputMissingError("market_prices_seed.csv / fact_wacc_input")


def should_use_live_market(prefer_live: Optional[bool] = None) -> bool:
    """Return True when live Yahoo Finance market quotes should be used instead of offline FY26 seed."""
    if prefer_live is not None:
        return bool(prefer_live)
    if os.getenv("YUKTI_OFFLINE_SSOT") == "1":
        return False
    if os.getenv("PYTEST_CURRENT_TEST") and os.getenv("YUKTI_TEST_LIVE_MARKET") != "1":
        return False
    return True


def load_market_price_for_dcf(
    prefer_live: Optional[bool] = None,
) -> Tuple[float, str, Dict[str, Any]]:
    """Return (share_price_inr, source_label, metadata) preferring live Yahoo Finance IOC.NS in production.

    In offline test mode (`PYTEST_CURRENT_TEST` without `YUKTI_TEST_LIVE_MARKET=1`, or `YUKTI_OFFLINE_SSOT=1`),
    delegates directly to `load_fy26_market_price_default()` so deterministic SSOT unit tests remain invariant.
    """
    if should_use_live_market(prefer_live):
        try:
            from app.market.oil_prices import get_oil_prices

            iocl_data = get_oil_prices("iocl")
            live_obj = iocl_data.get("live") or {}
            hist_obj = iocl_data.get("history") or {}
            px_opt = _opt_float(live_obj.get("price"))
            if px_opt is not None and px_opt > 0:
                px = round(px_opt, 2)
                stale = bool(iocl_data.get("stale"))
                as_of_raw = str(live_obj.get("as_of") or "")
                dt = as_of_raw[:10] if len(as_of_raw) >= 10 else str(hist_obj.get("last") or "live")

                brent_live: Optional[float] = None
                fx_live: Optional[float] = None
                try:
                    brent_live = _opt_float((get_oil_prices("brent").get("live") or {}).get("price"))
                except Exception:
                    pass
                try:
                    fx_live = _opt_float((get_oil_prices("inr").get("live") or {}).get("price"))
                except Exception:
                    pass

                feed_mode = "saved history" if stale else "live API"
                src_label = f"Yahoo Finance {feed_mode} (NSE:IOC {dt}: ₹{px:.2f})"
                return (
                    px,
                    src_label,
                    {
                        "ticker": "IOC.NS",
                        "date": dt,
                        "close_inr": px,
                        "live_inr": px,
                        "change_pct": _opt_float(live_obj.get("change_pct")),
                        "source_doc": "Yahoo Finance API (IOC.NS)",
                        "source_url": "https://finance.yahoo.com/quote/IOC.NS",
                        "live": not stale,
                        "stale": stale,
                        "brent_live_usd": round(brent_live, 2) if brent_live else None,
                        "fx_live_inr": round(fx_live, 2) if fx_live else None,
                    },
                )
        except Exception as exc:
            logger.warning(f"Live Yahoo Finance IOC.NS fetch unavailable for DCF, falling back to SSOT seed: {exc}")

    return load_fy26_market_price_default()
