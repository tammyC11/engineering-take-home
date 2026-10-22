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
CLINICIAN_READS = Counter(
    "clinician_reads_total", "Doctors opening a shared diary, by outcome.", ["outcome"]
)
for outcome in ("ok", "not_found", "error"):
    CLINICIAN_READS.labels(outcome)  # export zeros so alerts and rates work from the start
# O.Mon_1: any increase means a doctor was refused data because the read couldn't be recorded.
ACCESS_LOG_WRITE_FAILURES = Counter(
    "access_log_write_failures_total", "Clinician reads that could not be recorded."
)
LATENCY = Histogram(
    "http_request_duration_seconds", "HTTP request duration by route template.", ["method", "route"]
)
