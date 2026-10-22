"""Prometheus metrics, served on /metrics and scraped by the platform team."""

from prometheus_client import Counter, Histogram

REQUESTS = Counter(
    "http_requests_total",
    "HTTP requests by route template and status.",
    ["method", "route", "status"],
)
APP_EVENTS = Counter("app_events_total", "Product events sent by the app.", ["event"])
SHARE_CHANGES = Counter(
    "share_changes_total", "Diary shares created or revoked by patients.", ["action"]
)
LATENCY = Histogram(
    "http_request_duration_seconds", "HTTP request duration by route template.", ["method", "route"]
)
