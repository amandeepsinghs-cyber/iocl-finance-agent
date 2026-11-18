#!/usr/bin/env python3
"""Download official IOCL Annual Reports (FY17-FY26 = 2016-17 to 2025-26) from NSE Archives,
extract layout-preserving page text (`pdftotext -layout`), and upload PDFs to GCS (`gs://yukti-finance-iocl-docs/annual_reports/`).

Outputs:
- Raw PDFs (gitignored): `knowledge/public_sources/grounding_data/raw/IOCL_AR_FY20XX-YY.pdf`
- Extracted text (`\\f` per page): `knowledge/public_sources/grounding_data/text/IOCL_AR_FY20XX-YY.txt`
- Manifest with SHA-256, page counts & text stats: `knowledge/public_sources/grounding_data/IOCL_AR_MANIFEST.json`
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "knowledge" / "public_sources" / "grounding_data" / "raw"
TEXT_DIR = REPO_ROOT / "knowledge" / "public_sources" / "grounding_data" / "text"
MANIFEST_PATH = REPO_ROOT / "knowledge" / "public_sources" / "grounding_data" / "IOCL_AR_MANIFEST.json"

PROJECT_ID = os.getenv("TARGET_PROJECT") or os.getenv("YUKTI_GCP_PROJECT") or "yukti-finance-iocl"
DOCS_BUCKET = f"gs://{PROJECT_ID}-docs/annual_reports"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/pdf,application/zip,application/json,*/*",
    "Referer": "https://www.nseindia.com/get-quotes/equity?symbol=IOC",
}

TARGET_FYS = {
    ("2016", "2017"): ("FY17", "IOCL_AR_FY2016-17"),
    ("2017", "2018"): ("FY18", "IOCL_AR_FY2017-18"),
    ("2018", "2019"): ("FY19", "IOCL_AR_FY2018-19"),
    ("2019", "2020"): ("FY20", "IOCL_AR_FY2019-20"),
    ("2020", "2021"): ("FY21", "IOCL_AR_FY2020-21"),
    ("2021", "2022"): ("FY22", "IOCL_AR_FY2021-22"),
    ("2022", "2023"): ("FY23", "IOCL_AR_FY2022-23"),
    ("2023", "2024"): ("FY24", "IOCL_AR_FY2023-24"),
    ("2024", "2025"): ("FY25", "IOCL_AR_FY2024-25"),
    ("2025", "2026"): ("FY26", "IOCL_AR_FY2025-26"),
}


def candidate_urls(raw_url: str) -> List[str]:
    urls = [raw_url]
    if "nsearchives.nseindia.in/" in raw_url:
        urls.insert(0, raw_url.replace("nsearchives.nseindia.in/", "nsearchives.nseindia.com/"))
    elif "nsearchives.nseindia.com/" in raw_url:
        urls.append(raw_url.replace("nsearchives.nseindia.com/", "nsearchives.nseindia.in/"))
    return list(dict.fromkeys(urls))


def fetch_bytes(client: httpx.Client, raw_url: str) -> tuple[bytes, str]:
    last_err: Exception | None = None
    for u in candidate_urls(raw_url):
        for attempt in range(3):
            try:
                tmp_out = RAW_DIR / f"_tmp_dl_{os.getpid()}.bin"
                cmd = [
                    "curl", "-sS", "-fL", "--retry", "5", "--retry-delay", "2",
                    "--max-time", "300",
                    "-A", HEADERS["User-Agent"],
                    "-e", HEADERS["Referer"],
                    "-o", str(tmp_out),
                    u,
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if proc.returncode == 0 and tmp_out.exists() and tmp_out.stat().st_size > 50_000:
                    data = tmp_out.read_bytes()
                    tmp_out.unlink(missing_ok=True)
                    if data[:4] == b"%PDF" and b"%%EOF" not in data[-4096:]:
                        raise RuntimeError(f"Truncated PDF download ({len(data)} bytes, missing %%EOF)")
                    return data, u
                tmp_out.unlink(missing_ok=True)
            except Exception as exc:
                last_err = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Failed to download {raw_url}: {last_err}")


def extract_pdf_from_payload(payload: bytes, source_url: str) -> bytes:
    if payload[:4] == b"%PDF":
        return payload
    if zipfile.is_zipfile(io.BytesIO(payload)):
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            pdf_members = [m for m in zf.infolist() if not m.is_dir() and m.filename.lower().endswith(".pdf")]
            if not pdf_members:
                raise RuntimeError(f"No PDF inside ZIP from {source_url}: {[m.filename for m in zf.infolist()]}")
            # Pick the largest PDF (the full English Annual Report when supplementary notices exist)
            best = max(pdf_members, key=lambda m: m.file_size)
            print(f"    unzipped {best.filename} ({best.file_size:,} bytes)")
            return zf.read(best)
    raise RuntimeError(f"Unrecognized payload header from {source_url}: {payload[:16]!r}")


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    TEXT_DIR.mkdir(parents=True, exist_ok=True)

    manifest: List[Dict[str, Any]] = []

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=60.0) as client:
        client.get("https://www.nseindia.com")
        r = client.get(
            "https://www.nseindia.com/api/annual-reports?index=equities&symbol=IOC",
            headers={**HEADERS, "Accept": "application/json"},
        )
        r.raise_for_status()
        listing = r.json().get("data") or []
        (RAW_DIR / "NSE_API_annual-reports_IOC.json").write_text(json.dumps(listing, indent=2), encoding="utf-8")

        by_pair: Dict[tuple[str, str], str] = {}
        for row in listing:
            pair = (str(row.get("fromYr", "")).strip(), str(row.get("toYr", "")).strip())
            if pair in TARGET_FYS and pair not in by_pair and row.get("fileName"):
                by_pair[pair] = str(row["fileName"]).strip()

        for pair in sorted(TARGET_FYS.keys()):
            fy_code, stem = TARGET_FYS[pair]
            pdf_path = RAW_DIR / f"{stem}.pdf"
            txt_path = TEXT_DIR / f"{stem}.txt"
            raw_url = by_pair.get(pair)
            if not raw_url:
                print(f"[WARN] Missing NSE listing for {fy_code} {pair}")
                continue

            if pdf_path.exists() and pdf_path.stat().st_size > 100_000:
                print(f"[{fy_code}] Reusing cached PDF {pdf_path.name} ({pdf_path.stat().st_size:,} bytes)")
                used_url = raw_url
                pdf_bytes = pdf_path.read_bytes()
            else:
                print(f"[{fy_code}] Downloading {raw_url} ...", flush=True)
                payload, used_url = fetch_bytes(client, raw_url)
                pdf_bytes = extract_pdf_from_payload(payload, used_url)
                pdf_path.write_bytes(pdf_bytes)
                print(f"[{fy_code}] Saved {pdf_path.name} ({len(pdf_bytes):,} bytes)", flush=True)
                time.sleep(1.2)

            sha = hashlib.sha256(pdf_bytes).hexdigest()

            if not txt_path.exists() or txt_path.stat().st_size < 1000:
                subprocess.run(["pdftotext", "-layout", str(pdf_path), str(txt_path)], check=True)

            txt_content = txt_path.read_text(encoding="utf-8", errors="ignore")
            pages = txt_content.count("\f") + (1 if txt_content and not txt_content.endswith("\f") else 0)
            non_ws_chars = sum(1 for ch in txt_content if not ch.isspace())
            text_extractable = non_ws_chars > 20_000

            print(
                f"[{fy_code}] Text extracted -> {txt_path.name}: {pages} pages, "
                f"{len(txt_content):,} bytes, extractable={text_extractable}",
                flush=True,
            )

            manifest.append({
                "fiscal_year": fy_code,
                "from_year": pair[0],
                "to_year": pair[1],
                "pdf_file": f"grounding_data/raw/{pdf_path.name}",
                "text_file": f"grounding_data/text/{txt_path.name}",
                "source_url": used_url,
                "pdf_bytes": len(pdf_bytes),
                "sha256": sha,
                "pages": pages,
                "text_bytes": len(txt_content),
                "non_whitespace_chars": non_ws_chars,
                "text_extractable": text_extractable,
                "fetched_utc": datetime.now(timezone.utc).isoformat(),
            })

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {MANIFEST_PATH} ({len(manifest)} Annual Reports).")

    # Upload all downloaded IOCL Annual Report PDFs to GCS docs bucket
    env = {**os.environ, "CLOUDSDK_METRICS_ENVIRONMENT": "datacloud.jetski"}
    pdf_files = sorted(str(p) for p in RAW_DIR.glob("IOCL_AR_FY*.pdf"))
    if pdf_files:
        print(f"Uploading {len(pdf_files)} IOCL Annual Report PDFs to {DOCS_BUCKET}/ ...", flush=True)
        subprocess.run(
            ["gcloud", "storage", "cp", *pdf_files, f"{DOCS_BUCKET}/", f"--project={PROJECT_ID}"],
            env=env,
            check=True,
        )
        print("Uploaded all IOCL Annual Report PDFs to GCS successfully.")


if __name__ == "__main__":
    main()
