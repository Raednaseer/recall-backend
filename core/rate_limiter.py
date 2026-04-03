import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Request, status

from core.config import settings
from core.dependencies import get_redis
from core.security import get_current_user
from utils.logger import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """Redis sliding-window rate limiter.

    Usage as a FastAPI dependency::

        @router.post("/chat", dependencies=[Depends(RateLimiter(max_requests=20))])
    """

    def __init__(self, max_requests: int, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def __call__(
        self,
        request: Request,
        current_user: dict = Depends(get_current_user),
        redis: aioredis.Redis = Depends(get_redis),
    ):
        user_id = current_user["user_id"]
        endpoint = request.url.path
        key = f"rate_limit:{user_id}:{endpoint}"

        current = await redis.incr(key)
        if current == 1:
            await redis.expire(key, self.window_seconds)

        if current > self.max_requests:
            ttl = await redis.ttl(key)
            logger.warning(
                "Rate limit exceeded — user=%s endpoint=%s count=%d limit=%d",
                user_id, endpoint, current, self.max_requests,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {ttl} seconds.",
            )
