from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from core.dependencies import get_db
from core.security import get_current_user
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/history", tags=["Chat History"])


# =========================================================
# List conversations
# =========================================================
@router.get("/")
async def list_conversations(
    limit: int = Query(20, ge=1, le=100),
    skip: int = Query(0, ge=0),
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["user_id"]
    logger.info("Listing conversations — user=%s skip=%d limit=%d", user_id, skip, limit)

    cursor = (
        db.chat_history.find({"user_id": user_id})
        .sort("updated_at", -1)
        .skip(skip)
        .limit(limit)
    )

    conversations = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        conversations.append(doc)

    return {"conversations": conversations, "count": len(conversations)}


# =========================================================
# Get single conversation
# =========================================================
@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["user_id"]

    try:
        doc = await db.chat_history.find_one({"_id": ObjectId(conversation_id)})
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid conversation ID")

    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    if doc["user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your conversation")

    doc["_id"] = str(doc["_id"])
    logger.info("Fetched conversation=%s messages=%d", conversation_id, len(doc.get("messages", [])))
    return doc


# =========================================================
# Delete conversation
# =========================================================
@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["user_id"]

    try:
        doc = await db.chat_history.find_one({"_id": ObjectId(conversation_id)})
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid conversation ID")

    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    if doc["user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your conversation")

    await db.chat_history.delete_one({"_id": ObjectId(conversation_id)})
    logger.info("Deleted conversation=%s user=%s", conversation_id, user_id)

    return {"status": "deleted", "conversation_id": conversation_id}
