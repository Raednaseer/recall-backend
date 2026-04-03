from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, EmailStr

from core.dependencies import get_db
from core.security import create_access_token, get_current_user, hash_password, verify_password
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


# ---------------------
# Request / Response
# ---------------------
class AuthRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------------------
# Register
# ---------------------
@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: AuthRequest, db: AsyncIOMotorDatabase = Depends(get_db)):
    logger.info("Registration attempt — email=%s", body.email)
    existing = await db.users.find_one({"email": body.email})
    if existing:
        logger.warning("Registration conflict — email=%s already exists", body.email)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user_doc = {
        "email": body.email,
        "password": hash_password(body.password),
    }
    result = await db.users.insert_one(user_doc)
    logger.info("User registered — id=%s email=%s", result.inserted_id, body.email)

    token = create_access_token({"user_id": str(result.inserted_id), "email": body.email})
    return TokenResponse(access_token=token)


# ---------------------
# Login
# ---------------------
@router.post("/login", response_model=TokenResponse)
async def login(body: AuthRequest, db: AsyncIOMotorDatabase = Depends(get_db)):
    logger.info("Login attempt — email=%s", body.email)
    user = await db.users.find_one({"email": body.email})
    if not user or not verify_password(body.password, user["password"]):
        logger.warning("Login failed — email=%s", body.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    logger.info("Login successful — user_id=%s email=%s", user["_id"], user["email"])
    token = create_access_token({"user_id": str(user["_id"]), "email": user["email"]})
    return TokenResponse(access_token=token)


# ---------------------
# Token Refresh
# ---------------------
@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(current_user: dict = Depends(get_current_user)):
    """Issue a fresh token using the current valid token."""
    logger.info("Token refresh — user_id=%s", current_user["user_id"])
    new_token = create_access_token({
        "user_id": current_user["user_id"],
        "email": current_user["email"],
    })
    return TokenResponse(access_token=new_token)

