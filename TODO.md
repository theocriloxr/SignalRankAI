# Fix ImportError in web/app.py

## Steps:
1. [x] Add `count_active_subscriptions` function to `db/repository.py`
2. [x] Fix import and usage in `web/app.py`: replace `get_latest_active_api_token` with `get_api_token_owner`
3. [x] Test startup with `uvicorn web.app:app --host 0.0.0.0 --port 8000 --reload`
4. [ ] Verify /health endpoint works
5. [ ] Complete

