# Yukti IOCL — App Link

**app link:** https://yukti-iocl-u7thdacpua-el.a.run.app

_Last updated: 21-Nov-2026 (`yukti-iocl` v9 · revision `yukti-iocl-00009-f9v` — Indian Oil Corporation Limited Finance & Downstream Intelligence Agent)._

## 1. Cloud Run — Production (`yukti-finance-iocl` · `asia-south1`)
- **App link:** https://yukti-iocl-u7thdacpua-el.a.run.app (alias: https://yukti-iocl-304306246468.asia-south1.run.app)
- **Demo Practice Playbook:** https://yukti-iocl-u7thdacpua-el.a.run.app/demo
- **Architecture Portal ("How Yukti works"):** https://yukti-iocl-u7thdacpua-el.a.run.app/architecture/portal.html (and `/architecture`)
- **Active Revision:** `yukti-iocl-00009-f9v` (100% traffic)
- **Container Image:** `asia-south1-docker.pkg.dev/yukti-finance-iocl/yukti-repo/yukti-iocl:v9`
- **Runtime Service Account:** `yukti-iocl-sa@yukti-finance-iocl.iam.gserviceaccount.com`
- **Secret Manager Binding:** `YUKTI_PERSONA_SIGNING_KEY=yukti-persona-signing-key:latest`
- **Access:** Google Sign-In via **Identity-Aware Proxy (IAP)**. Approved account: `admin@amandeepsinghs.altostrat.com`.
  - Grant access to additional users:
    ```bash
    CLOUDSDK_METRICS_ENVIRONMENT=datacloud.jetski gcloud beta iap web add-iam-policy-binding \
      --project=yukti-finance-iocl --resource-type=cloud-run --service=yukti-iocl \
      --region=asia-south1 --member=user:NAME@DOMAIN --role=roles/iap.httpsResourceAccessor
    ```
  - Or tunnel locally with `gcloud`:
    ```bash
    gcloud run services proxy yukti-iocl --region=asia-south1 --project=yukti-finance-iocl --port=3400
    ```

## 2. Local Development (Isolated IOCL Ports — Never Collides with ONGC)
- **Frontend Single-Origin Server:** http://localhost:3400 (`cd yukti/frontend && PORT=3400 YUKTI_BACKEND_URL=http://127.0.0.1:8195 node server.js`)
- **FastAPI + ADK + Gemini Live Backend:** http://127.0.0.1:8195/health (`cd yukti/backend && TARGET_PROJECT=yukti-finance-iocl YUKTI_PLANNER=1 ./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8195`)
- **SSH Port-Forward from Laptop:** `ssh -L 3400:localhost:3400 amandeepsinghs.c.googlers.com`
