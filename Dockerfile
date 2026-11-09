# syntax=docker/dockerfile:1
FROM python:3.13-slim AS build
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
# Install exactly the locked versions, then the project itself without re-resolving.
RUN uv export --frozen --no-dev --extra postgres --no-emit-project -o /tmp/requirements.txt \
 && uv pip install --system --no-cache -r /tmp/requirements.txt \
 && uv pip install --system --no-cache --no-deps .

FROM python:3.13-slim
WORKDIR /app
RUN useradd --create-home --uid 10001 triage
COPY --from=build /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=build /usr/local/bin/uvicorn /usr/local/bin/triage-* /usr/local/bin/
# Patch OS packages and drop pip/setuptools (and their vendored libraries) from the runtime image:
# nothing installs packages at runtime, and they are the usual source of scanner findings.
RUN apt-get update && apt-get upgrade -y --no-install-recommends && rm -rf /var/lib/apt/lists/* \
 && python -m pip uninstall -y pip setuptools wheel || true \
 && rm -rf /usr/local/lib/python3.13/ensurepip
COPY runbooks ./runbooks
USER 10001
ENV RUNBOOKS_DIR=/app/runbooks PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz')"
CMD ["uvicorn", "triage.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
