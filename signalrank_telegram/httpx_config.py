import httpx

# Increase connection pool size and timeout for Telegram bot
httpx_client = httpx.AsyncClient(
    limits=httpx.Limits(max_connections=60, max_keepalive_connections=30),
    timeout=httpx.Timeout(20.0)
)
