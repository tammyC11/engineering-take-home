import logging
import time
import traceback
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.routing import APIRoute
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api import router
from app.metrics import LATENCY, REQUESTS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("diary.requests")


class WithholdExceptionMessages(logging.Filter):
    """Logs a crash's type and stack, not its message: Postgres errors quote the failing row,
    e.g. a patient's note (O.Log_4)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info and record.exc_info[0] is not None:
            error_type, _, stack = record.exc_info
            record.msg = f"{record.getMessage()}: {error_type.__name__} (message withheld)"
            record.args = ()
            record.exc_info = record.exc_text = None
            record.stack_info = "".join(traceback.format_tb(stack)).rstrip()
        return True


# Uvicorn logs unhandled exceptions here, with the full message.
logging.getLogger("uvicorn.error").addFilter(WithholdExceptionMessages())
# Uvicorn's access log prints raw paths, which carry patient IDs; log_requests below replaces it.
logging.getLogger("uvicorn.access").disabled = True

app = FastAPI(title="Symptom Diary API")
app.include_router(router)

# Prometheus sees no increase in a series whose first sample is already 12, so the first burst of
# errors after a restart would never alert. Start the series the alerts watch at zero.
for _route in router.routes:  # the router has no prefix, so paths match the route labels
    if isinstance(_route, APIRoute) and _route.path.startswith(
        ("/clinician/", "/shares", "/access-log")
    ):
        for _method in _route.methods:
            for _status in (500, 401, 403) if _route.path.startswith("/clinician/") else (500,):
                REQUESTS.labels(_method, _route.path, _status)


@app.middleware("http")
async def log_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    started = time.perf_counter()
    # A crash escapes call_next and only becomes a 500 further out; count it as one here, or
    # the 5xx alerts would miss exactly the failures they are for.
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        route = request.scope["route"].path if "route" in request.scope else "unmatched"
        REQUESTS.labels(request.method, route, status).inc()
        LATENCY.labels(request.method, route).observe(time.perf_counter() - started)
        # The route template, never the path or body: they carry patient IDs and health data
        # (O.Log_4).
        logger.info(
            "%s %s -> %s in %.0f ms",
            request.method,
            route,
            status,
            (time.perf_counter() - started) * 1000,
        )


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
