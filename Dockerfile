FROM python:3.11-slim@sha256:e41613d42d4891e4930f79523f93f81bbc7632584ec65e36ab055f41a800b41e AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Pin the Debian security updates as well as the base digest. The base predates
# DSA-6530-1 (PCRE2) and DSA-6531-1 (OpenSSL); installing libpq alone keeps those
# vulnerable inherited packages in the final image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc=4:14.2.0-1 libpq-dev=17.11-0+deb13u1 libpcre2-8-0=10.46-1~deb13u3 libssl3t64=3.5.7-1~deb13u3 openssl=3.5.7-1~deb13u3 openssl-provider-legacy=3.5.7-1~deb13u3 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.lock requirements-build-tools.txt requirements-market-data-sdk.lock release_certification_manifest.txt ./
RUN python -m venv "$VIRTUAL_ENV" \
    && python -m pip install --requirement requirements-build-tools.txt \
    && pip install --no-deps -r requirements.lock \
    && pip check

# Keep SDK dependencies out of the Telegram runtime (httpx versions conflict).
RUN python -m venv /opt/market-data-sdk \
    && /opt/market-data-sdk/bin/python -m pip install -r requirements-build-tools.txt \
    && /opt/market-data-sdk/bin/python -m pip install --no-build-isolation --require-hashes -r requirements-market-data-sdk.lock \
    && /opt/market-data-sdk/bin/python -m pip check

COPY . .
RUN /opt/market-data-sdk/bin/python -m unittest discover -s tests_sdk -v

# Build-time certification is intentionally deterministic and network-free
# except for dependency installation above. This prevents Railway from
# deploying an image whose release-critical regression set does not pass.
RUN python scripts/run_release_manifest.py --environment image --group image

FROM python:3.11-slim@sha256:e41613d42d4891e4930f79523f93f81bbc7632584ec65e36ab055f41a800b41e AS stripped-runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    MARKET_DATA_SDK_PYTHON=/opt/market-data-sdk/bin/python \
    SIGNALRANK_IMMUTABLE_RUNTIME=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5=17.11-0+deb13u1 ca-certificates=20250419 libpcre2-8-0=10.46-1~deb13u3 libssl3t64=3.5.7-1~deb13u3 openssl=3.5.7-1~deb13u3 openssl-provider-legacy=3.5.7-1~deb13u3 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 signalrank \
    && useradd --system --uid 10001 --gid signalrank --create-home --home-dir /home/signalrank signalrank

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/market-data-sdk /opt/market-data-sdk
COPY --from=builder --chown=signalrank:signalrank /app /app

RUN python -m pip uninstall --yes pip \
    && /opt/market-data-sdk/bin/python -m pip uninstall --yes pip \
    && rm -rf /usr/local/lib/python3.11/site-packages/pip /usr/local/lib/python3.11/site-packages/pip-*.dist-info \
        /usr/local/lib/python3.11/site-packages/setuptools /usr/local/lib/python3.11/site-packages/setuptools-*.dist-info \
        /usr/local/lib/python3.11/site-packages/_distutils_hack /usr/local/lib/python3.11/site-packages/pkg_resources \
        /usr/local/lib/python3.11/site-packages/wheel /usr/local/lib/python3.11/site-packages/wheel-*.dist-info \
        /usr/local/lib/python3.11/ensurepip \
    && rm -f /usr/local/lib/python3.11/site-packages/distutils-precedence.pth \
        /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.11 /usr/local/bin/wheel \
    && python scripts/verify_runtime_dependencies.py \
    && /opt/market-data-sdk/bin/python scripts/verify_runtime_dependencies.py \
    && python -c "import importlib.util; assert importlib.util.find_spec('pip') is None" \
    && /opt/market-data-sdk/bin/python -c "import importlib.util; assert importlib.util.find_spec('pip') is None" \
    && /usr/local/bin/python -c "import importlib.util; assert importlib.util.find_spec('pip') is None; assert importlib.util.find_spec('setuptools') is None" \
    && python -c "import numpy, pandas, scipy, sklearn, xgboost, asyncpg, psycopg2" \
    && /opt/market-data-sdk/bin/python -m unittest discover -s tests_sdk -v \
    && chmod +x /app/start.sh

# Publish the stripped filesystem, including OS package metadata for auditing.
FROM scratch AS runtime
COPY --from=stripped-runtime / /
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    MARKET_DATA_SDK_PYTHON=/opt/market-data-sdk/bin/python \
    SIGNALRANK_IMMUTABLE_RUNTIME=1 \
    PATH="/opt/venv/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin"
WORKDIR /app
USER 10001:10001

EXPOSE 8080
ENTRYPOINT ["/bin/bash", "/app/start.sh"]
