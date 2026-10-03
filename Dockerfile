FROM python:3.11-slim@sha256:e41613d42d4891e4930f79523f93f81bbc7632584ec65e36ab055f41a800b41e AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.lock requirements-build-tools.txt release_certification_manifest.txt ./
RUN python -m venv "$VIRTUAL_ENV" \
    && python -m pip install --requirement requirements-build-tools.txt \
    && pip install --no-deps -r requirements.lock \
    && pip check

COPY . .

# Build-time certification is intentionally deterministic and network-free
# except for dependency installation above. This prevents Railway from
# deploying an image whose release-critical regression set does not pass.
RUN python scripts/run_release_manifest.py --environment image --group image

FROM python:3.11-slim@sha256:e41613d42d4891e4930f79523f93f81bbc7632584ec65e36ab055f41a800b41e AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system signalrank \
    && useradd --system --gid signalrank --create-home --home-dir /home/signalrank signalrank

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder --chown=signalrank:signalrank /app /app

RUN chmod +x /app/start.sh
USER signalrank

EXPOSE 8080
ENTRYPOINT ["/bin/bash", "/app/start.sh"]
