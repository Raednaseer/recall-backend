from contextlib import asynccontextmanager

import certifi
import redis.asyncio as redis
from fastapi import FastAPI
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from motor.motor_asyncio import AsyncIOMotorClient
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PayloadSchemaType

from core.config import settings
from routes.rag import router as rag_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Redis
    app.state.redis = redis.from_url(settings.redis_url, decode_responses=True)

    # MongoDB
    app.state.mongo = AsyncIOMotorClient(settings.mongo_uri, tlsCAFile=certifi.where())
    app.state.db = app.state.mongo[settings.mongo_db_name]

    # Embeddings — loaded once, reused everywhere
    app.state.embeddings = GoogleGenerativeAIEmbeddings(
        model=settings.embedding_model,
        google_api_key=settings.google_api_key,
    )

    # Qdrant
    app.state.qdrant_client = QdrantClient(
        url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=120)

    # Create collection if it doesn't exist
    existing = [c.name for c in app.state.qdrant_client.get_collections().collections]
    if settings.qdrant_collection_name not in existing:
        app.state.qdrant_client.create_collection(
            collection_name=settings.qdrant_collection_name,
            vectors_config=VectorParams(size=3072, distance=Distance.COSINE),
        )

    # Vectorstore
    app.state.vectorstore = QdrantVectorStore(
        client=app.state.qdrant_client,
        collection_name=settings.qdrant_collection_name,
        embedding=app.state.embeddings,
    )

    app.state.qdrant_client.create_payload_index(
        collection_name=settings.qdrant_collection_name,
        field_name="metadata.user_id",
        field_schema=PayloadSchemaType.KEYWORD,
    )

    yield

    app.state.mongo.close()
    await app.state.redis.aclose()


app = FastAPI(title="Recall", version="1.0.0", lifespan=lifespan)

app.include_router(rag_router)
