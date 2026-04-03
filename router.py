from fastapi import Depends, HTTPException, APIRouter
from bson import ObjectId
import json
from models import Product
from dependencies import get_db, get_redis
from motor.motor_asyncio import AsyncIOMotorClient
import redis.asyncio as redis


router = APIRouter(prefix="/products", tags=["Products"])

@router.post("/")
async def create_product(
    product: Product,
    db: AsyncIOMotorClient = Depends(get_db),
    client: redis.Redis = Depends(get_redis),
):
    result = await db.products.insert_one(product.model_dump())
    inserted_id = str(result.inserted_id)

    # Warm the cache immediately after insert
    await client.set(f"product:{inserted_id}", product.model_dump_json(), ex=300)

    return {"id": inserted_id}


@router.get("/{id}")
async def get_product(
    id: str,
    db: AsyncIOMotorClient = Depends(get_db),
    client: redis.Redis = Depends(get_redis),
):
    # 1. Check Redis first
    cached = await client.get(f"product:{id}")
    if cached:
        print(f"[CACHE HIT] product:{id}")
        return json.loads(cached)

    # 2. Miss → fetch from MongoDB
    print(f"[CACHE MISS] product:{id} → querying MongoDB")
    product = await db.products.find_one({"_id": ObjectId(id)})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    product["_id"] = str(product["_id"])  # ObjectId isn't JSON serializable

    # 3. Store in Redis for next request
    await client.set(f"product:{id}", json.dumps(product), ex=300)

    return product


@router.delete("/{id}")
async def delete_product(
    id: str,
    db: AsyncIOMotorClient = Depends(get_db),
    client: redis.Redis = Depends(get_redis),
):
    result = await db.products.delete_one({"_id": ObjectId(id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")

    await client.delete(f"product:{id}")  # invalidate cache
    return {"status": "deleted"}
