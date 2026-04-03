from contextlib import asynccontextmanager

import certifi
import redis.asyncio as redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from motor.motor_asyncio import AsyncIOMotorClient
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PayloadSchemaType

from core.config import settings
from core.exceptions import register_exception_handlers
from routes.auth import router as auth_router
from routes.chat_history import router as history_router
from routes.health import router as health_router
from routes.rag import router as rag_router
from utils.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Recall application...")

    # Redis
    app.state.redis = redis.from_url(settings.redis_url, decode_responses=True)
    logger.info("Redis connected")

    # MongoDB
    app.state.mongo = AsyncIOMotorClient(settings.mongo_uri, tlsCAFile=certifi.where())
    app.state.db = app.state.mongo[settings.mongo_db_name]
    logger.info("MongoDB connected — db=%s", settings.mongo_db_name)

    # Embeddings — loaded once, reused everywhere
    app.state.embeddings = GoogleGenerativeAIEmbeddings(
        model=settings.embedding_model,
        google_api_key=settings.google_api_key,
    )
    logger.info("Embeddings model loaded — %s", settings.embedding_model)

    # Qdrant
    app.state.qdrant_client = QdrantClient(
        url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=120)
    logger.info("Qdrant client connected")

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
    app.state.qdrant_client.create_payload_index(
        collection_name=settings.qdrant_collection_name,
        field_name="metadata.collection",
        field_schema=PayloadSchemaType.KEYWORD,
    )
    logger.info("Payload indexes ensured — metadata.user_id, metadata.collection")

    logger.info("Application startup complete ✓")
    yield
    logger.info("Shutting down...")

    app.state.mongo.close()
    await app.state.redis.aclose()


app = FastAPI(title="Recall", version="2.0.0", lifespan=lifespan)

# Exception handlers
register_exception_handlers(app)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(rag_router)
app.include_router(history_router)
