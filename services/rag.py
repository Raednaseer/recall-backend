from langchain_google_genai import GoogleGenerativeAIEmbeddings

from core.config import settings

embeddings = GoogleGenerativeAIEmbeddings(
    model="models/text-embedding-004",
    google_api_key=settings.google_api_key,
)
