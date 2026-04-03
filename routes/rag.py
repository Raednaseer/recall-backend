import tempfile
import uuid
from collections.abc import AsyncIterable
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.sse import EventSourceResponse
from langchain_community.document_loaders import PyMuPDFLoader, TextLoader
from langchain_groq import ChatGroq
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue, PointIdsList

from core.config import settings
from core.dependencies import get_db, get_embeddings, get_qdrant_client, get_vectorstore
from core.rate_limiter import RateLimiter
from core.security import get_current_user
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/rag", tags=["RAG"])


# ─────────────────────────────────────────────
# Request / Response models
# ─────────────────────────────────────────────
class ChatRequest(BaseModel):
    query: str
    conversation_id: str | None = None
    collection: str = "default"


class StreamChunk(BaseModel):
    content: str


# ─────────────────────────────────────────────
# Upload
# ─────────────────────────────────────────────
@router.post(
    "/upload",
    dependencies=[Depends(RateLimiter(max_requests=settings.rate_limit_upload))],
)
async def upload_file(
    file: UploadFile = File(...),
    collection: str = Query("default"),
    embeddings=Depends(get_embeddings),
    vectorstore: QdrantVectorStore = Depends(get_vectorstore),
    qdrant_client: QdrantClient = Depends(get_qdrant_client),
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["user_id"]
    logger.info("Upload started — user=%s file=%s type=%s collection=%s", user_id, file.filename, file.content_type, collection)

    # ── Validate content type ──
    if file.content_type not in settings.allowed_content_types:
        logger.warning("Rejected upload — unsupported type=%s", file.content_type)
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {file.content_type}. Allowed: {settings.allowed_content_types}",
        )

    # ── Validate file size ──
    contents = await file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(contents) > max_bytes:
        logger.warning("Rejected upload — size=%d exceeds max=%d", len(contents), max_bytes)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large ({len(contents) / 1024 / 1024:.1f} MB). Max: {settings.max_upload_size_mb} MB.",
        )

    # Save file temporarily
    suffix = ".pdf" if file.content_type == "application/pdf" else ".txt"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name
    logger.debug("Temp file saved to %s", tmp_path)

    # Load document
    if suffix == ".pdf":
        loader = PyMuPDFLoader(tmp_path)
    else:
        loader = TextLoader(tmp_path)

    docs = loader.load()

    # Split into chunks
    splitter = RecursiveCharacterTextSplitter(chunk_size=300, chunk_overlap=50)
    chunks = splitter.split_documents(docs)

    # Generate deterministic IDs so we can track & delete later
    point_ids = [str(uuid.uuid4()) for _ in chunks]

    # Attach metadata
    for chunk in chunks:
        chunk.metadata["user_id"] = user_id
        chunk.metadata["filename"] = file.filename
        chunk.metadata["collection"] = collection

    logger.info("Inserting %d chunks into Qdrant for user=%s", len(chunks), user_id)

    # Batch insert into Qdrant
    BATCH_SIZE = 50
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        batch_ids = point_ids[i : i + BATCH_SIZE]
        vectorstore.add_documents(batch, ids=batch_ids)
        logger.debug("Batch %d–%d inserted", i, i + len(batch))

    # Save file metadata in MongoDB
    file_doc = {
        "user_id": user_id,
        "filename": file.filename,
        "content_type": file.content_type,
        "collection": collection,
        "chunk_count": len(chunks),
        "qdrant_point_ids": point_ids,
        "uploaded_at": datetime.now(timezone.utc),
    }
    result = await db.files.insert_one(file_doc)
    logger.info("Upload complete — file_id=%s chunks=%d collection=%s", result.inserted_id, len(chunks), collection)

    return {
        "status": "uploaded",
        "file_id": str(result.inserted_id),
        "filename": file.filename,
        "collection": collection,
        "chunks": len(chunks),
    }


# ─────────────────────────────────────────────
# List files
# ─────────────────────────────────────────────
@router.get("/files")
async def list_files(
    collection: str | None = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["user_id"]
    logger.info("Listing files for user=%s collection=%s", user_id, collection)

    query = {"user_id": user_id}
    if collection:
        query["collection"] = collection

    cursor = db.files.find(query, {"qdrant_point_ids": 0})
    files = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        files.append(doc)

    logger.info("Found %d files for user=%s", len(files), user_id)
    return {"files": files, "count": len(files)}


# ─────────────────────────────────────────────
# Delete file
# ─────────────────────────────────────────────
@router.delete("/files/{file_id}")
async def delete_file(
    file_id: str,
    qdrant_client: QdrantClient = Depends(get_qdrant_client),
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["user_id"]
    logger.info("Delete requested — user=%s file_id=%s", user_id, file_id)

    try:
        file_doc = await db.files.find_one({"_id": ObjectId(file_id)})
    except Exception:
        logger.warning("Invalid file ID format: %s", file_id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file ID")

    if not file_doc:
        logger.warning("File not found: %s", file_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    if file_doc["user_id"] != user_id:
        logger.warning("Forbidden delete attempt — user=%s tried file=%s (owner=%s)", user_id, file_id, file_doc["user_id"])
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your file")

    point_ids = file_doc["qdrant_point_ids"]
    if point_ids:
        qdrant_client.delete(
            collection_name=settings.qdrant_collection_name,
            points_selector=PointIdsList(points=point_ids),
        )
        logger.info("Deleted %d vectors from Qdrant for file=%s", len(point_ids), file_id)

    await db.files.delete_one({"_id": ObjectId(file_id)})
    logger.info("File record deleted from MongoDB — file_id=%s filename=%s", file_id, file_doc["filename"])

    return {
        "status": "deleted",
        "file_id": file_id,
        "filename": file_doc["filename"],
        "chunks_removed": len(point_ids),
    }


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def _build_qdrant_filter(user_id: str, collection: str | None = None) -> Filter:
    """Build Qdrant filter for user + optional collection."""
    conditions = [
        FieldCondition(key="metadata.user_id", match=MatchValue(value=user_id)),
    ]
    if collection:
        conditions.append(
            FieldCondition(key="metadata.collection", match=MatchValue(value=collection)),
        )
    return Filter(must=conditions)


def _build_prompt(context: str, query: str) -> str:
    return f"""You are a helpful assistant. Answer ONLY from the provided context.
If the answer is not in the context, say "I don't know".

Context:
{context}

Question:
{query}"""


async def _save_to_history(
    db: AsyncIOMotorDatabase,
    user_id: str,
    query: str,
    answer: str,
    sources: list,
    conversation_id: str | None = None,
):
    """Persist Q&A pair to MongoDB chat_history."""
    now = datetime.now(timezone.utc)
    message = {"query": query, "answer": answer, "sources": sources, "timestamp": now}

    if conversation_id:
        # Append to existing conversation
        await db.chat_history.update_one(
            {"_id": ObjectId(conversation_id), "user_id": user_id},
            {"$push": {"messages": message}, "$set": {"updated_at": now}},
        )
    else:
        # Create new conversation
        doc = {
            "user_id": user_id,
            "title": query[:80],
            "messages": [message],
            "created_at": now,
            "updated_at": now,
        }
        result = await db.chat_history.insert_one(doc)
        conversation_id = str(result.inserted_id)

    return conversation_id


# ─────────────────────────────────────────────
# Chat (standard JSON response)
# ─────────────────────────────────────────────
@router.post(
    "/chat",
    dependencies=[Depends(RateLimiter(max_requests=settings.rate_limit_chat))],
)
async def chat_with_docs(
    body: ChatRequest,
    vectorstore: QdrantVectorStore = Depends(get_vectorstore),
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["user_id"]
    logger.info("Chat query — user=%s query=%s collection=%s", user_id, body.query[:80], body.collection)

    docs = vectorstore.similarity_search(
        body.query,
        k=5,
        filter=_build_qdrant_filter(user_id, body.collection),
    )

    logger.debug("Retrieved %d docs from Qdrant", len(docs))

    if not docs:
        logger.info("No relevant docs found for user=%s", user_id)
        return {"answer": "No relevant documents found for this user.", "sources": [], "conversation_id": None}

    context = "\n\n".join([doc.page_content for doc in docs])

    llm = ChatGroq(api_key=settings.groq_api_key, model=settings.groq_model, temperature=0.2)
    prompt = _build_prompt(context, body.query)
    response = llm.invoke(prompt)
    logger.info("LLM response generated — length=%d", len(response.content))

    sources = [doc.metadata for doc in docs]
    conversation_id = await _save_to_history(db, user_id, body.query, response.content, sources, body.conversation_id)

    return {"answer": response.content, "sources": sources, "conversation_id": conversation_id}


# ─────────────────────────────────────────────
# Chat (SSE streaming)
# ─────────────────────────────────────────────
@router.post(
    "/chat/stream",
    response_class=EventSourceResponse,
    dependencies=[Depends(RateLimiter(max_requests=settings.rate_limit_chat))],
)
async def chat_stream(
    body: ChatRequest,
    vectorstore: QdrantVectorStore = Depends(get_vectorstore),
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> AsyncIterable[StreamChunk]:
    user_id = current_user["user_id"]
    logger.info("Stream chat — user=%s query=%s collection=%s", user_id, body.query[:80], body.collection)

    docs = vectorstore.similarity_search(
        body.query,
        k=5,
        filter=_build_qdrant_filter(user_id, body.collection),
    )

    if not docs:
        yield StreamChunk(content="No relevant documents found for this user.")
        return

    context = "\n\n".join([doc.page_content for doc in docs])

    llm = ChatGroq(api_key=settings.groq_api_key, model=settings.groq_model, temperature=0.2)
    prompt = _build_prompt(context, body.query)

    full_response = ""
    async for chunk in llm.astream(prompt):
        if chunk.content:
            full_response += chunk.content
            yield StreamChunk(content=chunk.content)

    sources = [doc.metadata for doc in docs]
    await _save_to_history(db, user_id, body.query, full_response, sources, body.conversation_id)
    logger.info("Stream complete — length=%d", len(full_response))
