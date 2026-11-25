import redis
from app.config import settings

r = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=1.0,
    socket_timeout=1.0,
)


def redis_healthy() -> bool:
    try:
        return bool(r.ping())
    except Exception:
        return False
