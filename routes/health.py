from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from qdrant_client import QdrantClient
import redis.asyncio as aioredis

from core.dependencies import get_db, get_qdrant_client, get_redis
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check(
    db: AsyncIOMotorDatabase = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    qdrant_client: QdrantClient = Depends(get_qdrant_client),
):
    results = {}

    # MongoDB
    try:
        await db.command("ping")
        results["mongodb"] = "healthy"
    except Exception as exc:
        logger.error("MongoDB health check failed: %s", exc)
        results["mongodb"] = "unhealthy"

    # Redis
    try:
        await redis.ping()
        results["redis"] = "healthy"
    except Exception as exc:
        logger.error("Redis health check failed: %s", exc)
        results["redis"] = "unhealthy"

    # Qdrant
    try:
        qdrant_client.get_collections()
        results["qdrant"] = "healthy"
    except Exception as exc:
        logger.error("Qdrant health check failed: %s", exc)
        results["qdrant"] = "unhealthy"

    overall = all(v == "healthy" for v in results.values())
    results["status"] = "ok" if overall else "degraded"

    logger.info("Health check — %s", results)
    return results
