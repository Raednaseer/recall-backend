from fastapi import Request
import redis.asyncio as redis
from motor.motor_asyncio import AsyncIOMotorDatabase

def get_db(request: Request) -> AsyncIOMotorDatabase:
    return request.app.state.db

def get_redis(request: Request) -> redis.Redis:
    return request.app.state.redis