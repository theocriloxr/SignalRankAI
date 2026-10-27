from typing import Callable, Awaitable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from utils.context import generate_correlation_id, set_correlation_id, reset_correlation_id


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        # Check if a correlation ID is already in the headers
        corr_id = request.headers.get("X-Correlation-ID")
        if not corr_id:
            corr_id = generate_correlation_id()

        token = set_correlation_id(corr_id)

        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = corr_id
            return response
        finally:
            reset_correlation_id(token)
