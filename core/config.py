from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    app_name: str = "RECALL"
    debug: bool = False

    # Upload Validation
    max_upload_size_mb: int = 10
    allowed_content_types: list[str] = ["application/pdf", "text/plain"]

    # Rate Limiting (requests per minute)
    rate_limit_chat: int = 20
    rate_limit_upload: int = 5

    # CORS
    cors_origins: list[str] = ["*"]

    # MongoDB
    mongo_uri: str
    mongo_db_name: str

    # Redis
    redis_url: str

    # Qdrant
    qdrant_url: str
    qdrant_api_key: str
    qdrant_collection_name: str = "recall_docs"

    # Groq
    groq_api_key: str
    groq_model: str

    # JWT Auth
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60

    # Google Embeddings
    google_api_key: str
    embedding_model: str = "models/gemini-embedding-001"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
