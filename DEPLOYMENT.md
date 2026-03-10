# Deployment notes for SignalRankAI

This file documents recommended deployment settings and steps (Railway friendly).

- Build: Only install dependencies during build. Don't attempt DB migrations during image build because the database is often not reachable from the builder.
  - Recommended `railway.json.build.buildCommand`: `pip install -r requirements.txt`

- Startup: Run migrations and any startup checks at container start. `start.sh` already runs:
  - `pip install -r requirements.txt` if `requirements.txt` exists (useful for local/dev runs)
  - `python -m alembic upgrade head` (guarded by `DATABASE_URL` check)
  - Then launches the configured `RUN_MODE` (web/engine/bot/worker)

- Environment variables (required / recommended):
  - `DATABASE_URL` - required for DB-backed services
  - `TELEGRAM_TOKEN` / `TELEGRAM_BOT_TOKEN` - for Telegram integration
  - `PAYSTACK_SECRET_KEY` / other API keys - set via Railway environment settings
  - `RUN_MODE` - override to run a specific service (`web`, `bot`, `engine`, `worker`, or `all`)
  - `AUTO_MIGRATE` - (optional) project supports runtime auto-migration via `db.auto_ops` when present

- Railway specifics & tips (Free tier):
  - Do not run DB migrations in the build step: builders can't reach your managed DB.
  - Use the `startCommand` value `./start.sh` so migrations run at container start.
  - Keep the image small: `python:3.11-slim` is used in `Dockerfile`.
  - Add required environment variables in the Railway project settings (do not hardcode secrets in the repo).

- Local testing commands:

```bash
# build image locally
docker build -t signalrankai .

# run container (replace placeholders)
docker run --rm -e DATABASE_URL=postgresql://user:pass@host:5432/db -e TELEGRAM_TOKEN=xxx -p 8000:8000 signalrankai

# run migrations manually
python -m alembic upgrade head
```

If you'd like, I can:
- Add a small health endpoint implementation if `/health` isn't present (so Railway healthchecks pass).
- Add a `Dockerfile.production` multi-stage build for smaller images.
- Add a GitHub Actions pipeline to run tests and linting on PRs.
