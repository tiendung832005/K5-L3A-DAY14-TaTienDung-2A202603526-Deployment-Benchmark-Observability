import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if hasattr(record, "extra_fields"):
            payload.update(record.extra_fields)
        return json.dumps(payload, ensure_ascii=False)


handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
root_logger = logging.getLogger()
root_logger.handlers = [handler]
root_logger.setLevel(logging.INFO)
logger = logging.getLogger("agent")

shutting_down = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global shutting_down
    shutting_down = False
    logger.info("startup", extra={"extra_fields": {"event": "startup"}})
    yield
    shutting_down = True
    logger.info("shutdown", extra={"extra_fields": {"event": "shutdown"}})


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception:
        status_code = 500
        ms = round((time.perf_counter() - start) * 1000, 2)
        logger.error(
            "request_error",
            extra={"extra_fields": {"event": "request", "path": request.url.path, "status": status_code, "ms": ms}},
        )
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        "request",
        extra={"extra_fields": {"event": "request", "path": request.url.path, "status": status_code, "ms": ms}},
    )
    return response


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    if shutting_down or not redis_healthy():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not ready",
        )
    return {"status": "ready"}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)
    check_budget()

    answer = llm_ask(body.question)
    input_tokens = max(1, len(body.question) // 4)
    output_tokens = max(1, len(answer) // 4)
    cost_usd = record_cost(input_tokens, output_tokens)

    return {
        "question": body.question,
        "answer": answer,
        "cost_usd": cost_usd,
    }
