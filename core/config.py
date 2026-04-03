from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    app_name: str = "RECALL"
    debug: bool = False

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

    # Google Embeddings
    google_api_key: str
    embedding_model: str = "models/gemini-embedding-001"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
