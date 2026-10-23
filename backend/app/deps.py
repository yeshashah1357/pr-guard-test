import time
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from redis import Redis
from rq import Queue

from app.config import get_settings


@lru_cache
def get_redis() -> Redis:
    return Redis.from_url(get_settings().redis_url)


def get_queue(redis: Annotated[Redis, Depends(get_redis)]) -> Queue:
    return Queue("reviews", connection=redis)


def login_rate_limit(request: Request, redis: Annotated[Redis, Depends(get_redis)]) -> None:
    """Fixed-window limit per client IP, shared across API replicas through Redis."""
    window = 60
    limit = get_settings().login_rate_limit_per_minute
    client = request.client.host if request.client else "unknown"
    key = f"ratelimit:login:{client}:{int(time.time() // window)}"
    count = redis.incr(key)
    if count == 1:
        redis.expire(key, window)
    if count > limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many login attempts, try again shortly",
            headers={"Retry-After": str(window)},
        )
