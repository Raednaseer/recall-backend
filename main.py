import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
import redis.asyncio as redis
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from router import router
import certifi

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = redis.from_url(REDIS_URL, decode_responses=True)

    # MongoDB
    uri = os.getenv("MONGO_URI")
    print(uri)
    app.state.mongo = AsyncIOMotorClient(os.getenv("MONGO_URI"), tlsCAFile=certifi.where())
    app.state.db = app.state.mongo[os.getenv("MONGO_DB_NAME")]

    yield
    app.state.mongo.close()
    await app.state.redis.aclose()


app = FastAPI(title="TestAPP", version="1.0.0", lifespan=lifespan)


@app.get("/")
def main():
    return {"message": "Hello World"}


@app.get("/health")
def health():
    return {"message": "healthy"}

app.include_router(router)
