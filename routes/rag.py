import tempfile

from fastapi import APIRouter, Body, Depends, File, UploadFile
from langchain_community.document_loaders import PyMuPDFLoader, TextLoader
from langchain_groq import ChatGroq
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client.models import FieldCondition, Filter, MatchValue

from core.config import settings
from core.dependencies import get_embeddings, get_vectorstore

router = APIRouter(prefix="/rag", tags=["RAG"])


@router.post("/upload")
async def upload_file(
    user_id: str,
    file: UploadFile = File(...),
    embeddings=Depends(get_embeddings),
    vectorstore: QdrantVectorStore = Depends(get_vectorstore),
):
    # -------------------------
    # Save file temporarily
    # -------------------------
    suffix = ".pdf" if file.content_type == "application/pdf" else ".txt"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    # -------------------------
    # Load document
    # -------------------------
    if suffix == ".pdf":
        loader = PyMuPDFLoader(tmp_path)  # more robust than PyPDFLoader
    else:
        loader = TextLoader(tmp_path)

    docs = loader.load()

    # -------------------------
    # Split into chunks
    # -------------------------
    splitter = RecursiveCharacterTextSplitter(chunk_size=300, chunk_overlap=50)
    chunks = splitter.split_documents(docs)

    # -------------------------
    # Attach metadata
    # -------------------------
    for chunk in chunks:
        chunk.metadata["user_id"] = user_id

    print(f"Uploading {len(chunks)} chunks...")

    # -------------------------
    # Batch insert into Qdrant
    # -------------------------
    BATCH_SIZE = 50

    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        vectorstore.add_documents(batch)

    # -------------------------
    # Response
    # -------------------------
    return {
        "status": "uploaded",
        "chunks": len(chunks),
        "user_id": user_id,
    }


@router.post("/chat")
async def chat_with_docs(
    user_id: str,
    query: str = Body(...),
    vectorstore: QdrantVectorStore = Depends(get_vectorstore),
):
    # -------------------------
    # Retrieve relevant docs
    # -------------------------
    docs = vectorstore.similarity_search(
        query,
        k=5,
        filter=Filter(
            must=[
                FieldCondition(
                    key="metadata.user_id",
                    match=MatchValue(value=user_id),
                )
            ]
        ),
    )

    if not docs:
        return {"answer": "No relevant documents found for this user.", "sources": []}

    # -------------------------
    # Build context
    # -------------------------
    context = "\n\n".join([doc.page_content for doc in docs])

    # -------------------------
    # LLM (Groq)
    # -------------------------
    llm = ChatGroq(
        api_key=settings.groq_api_key, model=settings.groq_model, temperature=0.2
    )

    prompt = f"""
You are a helpful assistant. Answer ONLY from the provided context.
If the answer is not in the context, say "I don't know".

Context:
{context}

Question:
{query}
"""

    response = llm.invoke(prompt)

    # -------------------------
    # Return response
    # -------------------------
    return {"answer": response.content, "sources": [doc.metadata for doc in docs]}
