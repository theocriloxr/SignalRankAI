# syntax=docker/dockerfile:1
FROM nixos/nix:2.18.1 AS builder

# Install Python, pip, and build tools
RUN nix-env -iA nixpkgs.python311 nixpkgs.python311Packages.pip nixpkgs.gcc

WORKDIR /app

# Copy only requirements first for caching
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the rest of the code
COPY . .

# Expose port for web (if needed)
EXPOSE 8000

# Use environment variables for secrets (do not hardcode or use ARG for secrets)
# Railway/production will inject these automatically

# Run migrations before starting (optional, can be handled by entrypoint/start.sh)
# RUN python -m alembic upgrade head || true

CMD ["python", "main.py"]
