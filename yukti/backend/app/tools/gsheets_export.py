"""Real Google Sheets export via Google Drive v3 API (.xlsx -> native Google Spreadsheet conversion).

Uploads a formula-driven `.xlsx` workbook with `mimeType=application/vnd.google-apps.spreadsheet` so
Google Drive converts every sheet, IndianOil formatting, Named Range, and Excel formula into a live
Google Sheet, shares it with the signed-in IAP user email (writer), and returns its `webViewLink`.

If the runtime service account lacks Drive storage quota or Workspace org policy restricts SA-owned
Drive files, returns `None` cleanly so `/api/export` falls back seamlessly to downloading the `.xlsx`.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger("yukti.tools.gsheets_export")

DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive",
]
DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"


def parse_iap_email(raw_header: Optional[str]) -> Optional[str]:
    """Extract plain email from Cloud Run IAP header `accounts.google.com:user@domain.com`."""
    if not raw_header:
        return None
    s = str(raw_header).strip()
    if ":" in s:
        s = s.split(":", 1)[1].strip()
    return s if ("@" in s and "." in s) else None


def _get_drive_token() -> Optional[str]:
    try:
        import google.auth
        import google.auth.transport.requests

        creds, _ = google.auth.default(scopes=DRIVE_SCOPES)
        creds.refresh(google.auth.transport.requests.Request())
        return getattr(creds, "token", None)
    except Exception as exc:
        logger.info("Google Sheets export skipped (Drive credentials unavailable: %s)", type(exc).__name__)
        return None


def upload_xlsx_to_google_sheets(
    xlsx_path: Path | str,
    title: str,
    share_email: Optional[str] = None,
    timeout_s: float = 15.0,
) -> Optional[Dict[str, Any]]:
    """Upload a local `.xlsx` file to Google Drive as a native Google Sheet.

    Returns `{"sheet_id": ..., "sheet_url": ..., "shared_with": ...}` on success, or `None` on fallback.
    """
    path = Path(xlsx_path)
    if not path.exists():
        return None

    token = _get_drive_token()
    if not token:
        return None

    clean_title = (title or path.stem).replace(".xlsx", "").strip()[:120] or "Yukti IOCL Export"
    metadata: Dict[str, Any] = {
        "name": clean_title,
        "mimeType": "application/vnd.google-apps.spreadsheet",
    }
    folder_id = os.getenv("YUKTI_GDRIVE_FOLDER_ID", "").strip()
    if folder_id:
        metadata["parents"] = [folder_id]

    headers = {"Authorization": f"Bearer {token}"}
    try:
        files = {
            "metadata": ("metadata", json.dumps(metadata), "application/json; charset=UTF-8"),
            "file": (
                path.name,
                path.read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        }
        resp = requests.post(
            DRIVE_UPLOAD_URL,
            params={
                "uploadType": "multipart",
                "fields": "id,webViewLink,name",
                "supportsAllDrives": "true",
            },
            headers=headers,
            files=files,
            timeout=timeout_s,
        )
        if resp.status_code not in (200, 201):
            logger.info(
                "Google Sheets Drive upload returned HTTP %s (falling back to .xlsx download): %s",
                resp.status_code,
                resp.text[:240],
            )
            return None

        data = resp.json()
        file_id = data.get("id")
        web_link = data.get("webViewLink") or (
            f"https://docs.google.com/spreadsheets/d/{file_id}/edit" if file_id else None
        )
        if not file_id or not web_link:
            return None

        target_email = share_email or os.getenv("YUKTI_SHEETS_SHARE_EMAIL", "").strip() or None
        shared_with: Optional[str] = None
        if target_email:
            perm_resp = requests.post(
                f"{DRIVE_FILES_URL}/{file_id}/permissions",
                params={"supportsAllDrives": "true", "sendNotificationEmail": "false"},
                headers={**headers, "Content-Type": "application/json"},
                json={"type": "user", "role": "writer", "emailAddress": target_email},
                timeout=timeout_s,
            )
            if perm_resp.status_code in (200, 201):
                shared_with = target_email
            else:
                logger.info("Google Sheets share with %s returned HTTP %s", target_email, perm_resp.status_code)

        return {
            "sheet_id": file_id,
            "sheet_url": web_link,
            "shared_with": shared_with,
        }
    except Exception as exc:
        logger.info("Google Sheets Drive upload failed (%s); falling back to .xlsx download", type(exc).__name__)
        return None
