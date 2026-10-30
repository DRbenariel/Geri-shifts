# Cloud Run image for the Geri-shifts API (DEPLOY_PLAN: Cloud Run, me-west1).
# Build from backend/:  docker build -t geri-api .
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY geri_core ./geri_core
COPY api ./api
# Copied in from the repo root before deploy (DEPLOY_PLAN): the manual problem scan runs its analyze_month.
COPY daily_report.py ./
# Cloud Run sets PORT. Env (Secret Manager): SESSION_SECRET, SPREADSHEET_URL, GSHEETS_CREDENTIALS;
# API_READ_ONLY stays 1 (the default) until the read-only phase is signed off.
CMD exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080}
