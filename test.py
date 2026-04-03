# test_embeddings.py
import asyncio
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from core.config import settings

def test_embeddings():
    embeddings = GoogleGenerativeAIEmbeddings(
        model=settings.embedding_model,
        google_api_key=settings.google_api_key,
    )

    test_texts = [
        "Hello, how are you?",
        "What is the capital of France?",
        "FastAPI is a modern web framework",
    ]

    print("Testing embeddings...\n")

    for text in test_texts:
        vector = embeddings.embed_query(text)
        print(f"Text    : {text}")
        print(f"Dims    : {len(vector)}")
        print(f"Sample  : {vector[:5]}")  # first 5 values
        print()

    # Test batch embedding
    vectors = embeddings.embed_documents(test_texts)
    print(f"Batch embedding: {len(vectors)} vectors, {len(vectors[0])} dims each")
    print("\n✅ Embeddings working correctly")


if __name__ == "__main__":
    test_embeddings()
# from google import genai
# from core.config import settings

# client = genai.Client(api_key=settings.google_api_key)

# models = client.models.list()
# for model in models:
#     print(f"Name: {model.name}")
#     print(f"Display Name: {model.display_name}")
#     print(f"Supported Actions: {model.supported_actions}")
#     print("-" * 20)
