import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api import router
from app.metrics import LATENCY, REQUESTS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("diary.requests")
# Uvicorn's access log prints raw paths, which carry patient IDs; log_requests below replaces it.
logging.getLogger("uvicorn.access").disabled = True

app = FastAPI(title="Symptom Diary API")
app.include_router(router)


@app.middleware("http")
async def log_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    started = time.perf_counter()
    response = await call_next(request)
    route = request.scope["route"].path if "route" in request.scope else "unmatched"
    REQUESTS.labels(request.method, route, response.status_code).inc()
    LATENCY.labels(request.method, route).observe(time.perf_counter() - started)
    # The route template, never the path or body: they carry patient IDs and health data (O.Log_4).
    logger.info(
        "%s %s -> %s in %.0f ms",
        request.method,
        route,
        response.status_code,
        (time.perf_counter() - started) * 1000,
    )
    return response


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
