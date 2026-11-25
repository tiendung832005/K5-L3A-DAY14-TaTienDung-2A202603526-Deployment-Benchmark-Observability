from datetime import datetime, timezone
from fastapi import HTTPException, status
from app.config import settings
from app.redis_client import r

PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _budget_key() -> str:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"cost_guard:daily:{day}"


def check_budget() -> None:
    try:
        spent = float(r.get(_budget_key()) or 0.0)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cost guard backend unavailable",
        ) from exc

    if spent >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Daily budget exceeded",
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    cost = (input_tokens / 1000.0) * PRICE_INPUT_PER_1K + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K
    key = _budget_key()
    try:
        r.incrbyfloat(key, cost)
        r.expire(key, 172800)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cost guard backend unavailable",
        ) from exc
    return round(cost, 8)
