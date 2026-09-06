# Build the FastAPI service without copying ignored source snapshots or secrets.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/app backend/app
RUN pip install --no-cache-dir ./backend

COPY backend/alembic.ini backend/alembic.ini
COPY backend/alembic backend/alembic
COPY data/source_manifest.yaml data/source_manifest.yaml

ENV PYTHONPATH=/app/backend
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--app-dir", "/app/backend", "--host", "0.0.0.0", "--port", "8000"]
