# Revenue Manager Agent — deployable web app (FastAPI + Deep Agent).
# The hosted Postgres is loaded separately (scripts/init_db.sh against the
# provisioned DATABASE_URL), so this image carries no Playwright/Chromium.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements-deploy.txt .
RUN pip install --no-cache-dir -r requirements-deploy.txt

# App code + the building blocks the agent imports at runtime.
COPY agent/ ./agent/
COPY tools/ ./tools/
COPY skills/ ./skills/
COPY sql/ ./sql/

EXPOSE 8000

# Honor the platform-provided PORT (Fly/Render/Railway set it); default 8000.
CMD ["sh", "-c", "uvicorn agent.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
