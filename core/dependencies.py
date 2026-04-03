import redis.asyncio as redis
from fastapi import Request
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from motor.motor_asyncio import AsyncIOMotorDatabase
from qdrant_client import QdrantClient


def get_db(request: Request) -> AsyncIOMotorDatabase:
    return request.app.state.db


def get_redis(request: Request) -> redis.Redis:
    return request.app.state.redis


def get_qdrant_client(request: Request) -> QdrantClient:
    return request.app.state.qdrant_client


def get_vectorstore(request: Request) -> QdrantVectorStore:
    return request.app.state.vectorstore


def get_embeddings(request: Request) -> GoogleGenerativeAIEmbeddings:
    return request.app.state.embeddings
