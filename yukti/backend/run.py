"""Entrypoint runner for Yukti AI Backend Server.
"""

import uvicorn
import os

os.environ.setdefault("YUKTI_CONTRACT_V3_FIELDS", "all")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8195))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"Starting Yukti AI Backend on {host}:{port}...")
    uvicorn.run("app.main:app", host=host, port=port, reload=False)
