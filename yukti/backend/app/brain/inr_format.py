"""Indian-numbering helpers for spoken / displayed figures (lakh-crore grouping)."""
from __future__ import annotations

from typing import Optional


def group_indian(n: int) -> str:
    """Group an integer with Indian digit grouping (e.g. 728445 -> '7,28,445')."""
    s = str(abs(int(n)))
    if len(s) <= 3:
        out = s
    else:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        out = ",".join(parts) + "," + tail
    return ("-" if n < 0 else "") + out


def fmt_inr_cr(v: Optional[float], signed: bool = False, unit: str = " crore") -> str:
    """₹ crore with Indian grouping; no decimals at or above ₹1,000 crore, one decimal below ₹100 crore."""
    if v is None:
        return "—"
    x = float(v)
    sign = ""
    if signed:
        sign = "+" if x > 0 else ("−" if x < 0 else "")
    elif x < 0:
        sign = "−"
    a = abs(x)
    if a >= 100:
        body = group_indian(int(round(a)))
    else:
        body = f"{a:.1f}".rstrip("0").rstrip(".")
    return f"{sign}₹{body}{unit}"


def fmt_pct(v: Optional[float], dp: int = 1, signed: bool = False) -> str:
    if v is None:
        return "—"
    s = f"{float(v):+.{dp}f}" if signed else f"{float(v):.{dp}f}"
    return f"{s}%"
