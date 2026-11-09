# syntax=docker/dockerfile:1
FROM python:3.13-slim AS build
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml README.md ./
COPY src ./src
RUN uv pip install --system --no-cache ".[postgres]"

FROM python:3.13-slim
WORKDIR /app
RUN useradd --create-home --uid 10001 triage
COPY --from=build /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=build /usr/local/bin/uvicorn /usr/local/bin/triage-* /usr/local/bin/
COPY runbooks ./runbooks
USER 10001
ENV RUNBOOKS_DIR=/app/runbooks PYTHONUNBUFFERED=1
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8080/healthz'); sys.exit(0)"
CMD ["uvicorn", "triage.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
