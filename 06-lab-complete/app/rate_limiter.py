import time
import uuid
from fastapi import HTTPException, status
from app.config import settings
from app.redis_client import r


def check_rate_limit(key: str) -> None:
    limit = settings.rate_limit_per_minute
    window = 60
    now = time.time()
    redis_key = f"rate_limit:{key}"

    try:
        pipe = r.pipeline()
        pipe.zremrangebyscore(redis_key, 0, now - window)
        pipe.zcard(redis_key)
        _, current_count = pipe.execute()

        if current_count >= limit:
            oldest = r.zrange(redis_key, 0, 0, withscores=True)
            retry_after = max(1, int(window - (now - oldest[0][1]))) if oldest else window
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )

        member = f"{now}:{uuid.uuid4()}"
        pipe = r.pipeline()
        pipe.zadd(redis_key, {member: now})
        pipe.expire(redis_key, window + 5)
        pipe.execute()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rate limiter backend unavailable",
        ) from exc
