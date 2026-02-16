"""
Middleware - Structured Logging, Rate Limiting, Request-IDs.
"""

import json
import logging
import time
import uuid
from collections import defaultdict
from contextvars import ContextVar
from datetime import datetime, timezone

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Request-ID als ContextVar (verfuegbar in allen async Tasks)
request_id_var: ContextVar[str] = ContextVar("request_id", default="")

logger = logging.getLogger(__name__)


class StructuredFormatter(logging.Formatter):
    """JSON Log Formatter fuer strukturiertes Logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        req_id = request_id_var.get("")
        if req_id:
            log_data["req_id"] = req_id

        if record.exc_info and record.exc_info[0]:
            log_data["exception"] = self.formatException(record.exc_info)

        for key in ("latency_ms", "method", "path", "status_code"):
            val = getattr(record, key, None)
            if val is not None:
                log_data[key] = val

        return json.dumps(log_data, ensure_ascii=False)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Setzt Request-ID und trackt Latenz."""

    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        request_id_var.set(req_id)

        start = time.monotonic()
        response = await call_next(request)
        latency_ms = round((time.monotonic() - start) * 1000, 1)

        response.headers["X-Request-ID"] = req_id
        response.headers["X-Response-Time"] = f"{latency_ms}ms"

        # Nur API-Calls loggen, nicht static/docs
        if request.url.path.startswith("/api/"):
            logger.info(
                "%s %s -> %d (%.1fms)",
                request.method, request.url.path, response.status_code, latency_ms,
                extra={
                    "method": request.method,
                    "path": str(request.url.path),
                    "status_code": response.status_code,
                    "latency_ms": latency_ms,
                },
            )

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Einfaches Rate Limiting pro IP-Adresse."""

    def __init__(self, app, max_requests: int = 30, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        # Bestimmte Pfade nicht limitieren
        skip_paths = {"/api/assistant/health", "/", "/docs", "/openapi.json", "/redoc"}
        if request.url.path in skip_paths:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()

        # Alte Eintraege bereinigen
        self._requests[client_ip] = [
            t for t in self._requests[client_ip]
            if now - t < self.window_seconds
        ]

        if len(self._requests[client_ip]) >= self.max_requests:
            return Response(
                content=json.dumps({"detail": "Zu viele Anfragen. Bitte warten."}),
                status_code=429,
                media_type="application/json",
            )

        self._requests[client_ip].append(now)
        return await call_next(request)
