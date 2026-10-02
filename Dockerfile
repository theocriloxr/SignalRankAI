FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies required by some Python packages (e.g. psycopg2)
RUN apt-get update \
	&& apt-get install -y --no-install-recommends gcc libpq-dev \
	&& rm -rf /var/lib/apt/lists/*

# Copy the declared direct requirements and the certified full dependency graph
# Copy the declared direct requirements and the certified full dependency graph
# first to preserve Docker layer caching. Runtime images install the lock, not
# a freshly-resolved graph.
COPY requirements.txt requirements.lock release_certification_manifest.txt ./

# Install the exact certified graph without allowing pip to re-resolve
# transitive dependencies. pip check fails the image build if the lock is
# internally inconsistent or misses a dependency required by installed
# packages.
RUN python -m pip install --upgrade pip setuptools wheel \
	&& pip install --no-deps -r requirements.lock \
	&& pip check

# Copy application code
COPY . .

# Release-critical regression gate. GitHub-hosted CI can be unavailable before a
# runner starts; these deterministic tests therefore also execute in the image
# build and must pass before Railway can deploy the artifact.
RUN echo "release_gate=20260925_web_fanout_db_pressure_v3" \
    && python -m compileall -q engine db data worker services ml signalrank_telegram web runtime core execution \
    && xargs -a release_certification_manifest.txt python -m pytest -q \
    && python scripts/generate_release_provenance.py --output-dir /tmp/signalrank-build-provenance --commit 0000000000000000000000000000000000000000 --branch build-gate --verify-self \
    && python scripts/generate_release_docs.py --provenance /tmp/signalrank-build-provenance/release-provenance.json --output /tmp/signalrank-build-provenance/RELEASE_NOTES.md \
    && python scripts/production_readiness_check.py

# Ensure start script is executable and use it as entrypoint so migrations/run-time
# setup happens when the container starts (not during image build).
RUN chmod +x ./start.sh || true

EXPOSE 8080

# Use the start script which runs migrations and then starts the appropriate service
ENTRYPOINT ["/bin/bash", "./start.sh"]
