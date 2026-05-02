FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies required by some Python packages (e.g. psycopg2)
RUN apt-get update \
	&& apt-get install -y --no-install-recommends gcc libpq-dev \
	&& rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker layer caching
COPY requirements.txt ./

# Ensure pip/tools are up-to-date and install Python deps
RUN python -m pip install --upgrade pip setuptools wheel \
	&& pip install -r requirements.txt

# Copy application code
COPY . .

# Ensure start script is executable and use it as entrypoint so migrations/run-time
# setup happens when the container starts (not during image build).
RUN chmod +x ./start.sh || true

EXPOSE 8080

# Use the start script which runs migrations and then starts the appropriate service
ENTRYPOINT ["/bin/bash", "./start.sh"]
