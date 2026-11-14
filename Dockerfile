# Product API image (repo root Dockerfile, as per the course repo layout)
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# pick up OS security fixes so Trivy stays green
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*
RUN useradd --uid 10001 --create-home phoenix
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
USER 10001
EXPOSE 8080
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}
# one worker + threads: keeps the in-memory /metrics counters consistent between scrapes
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--access-logfile", "-", "app:app"]
