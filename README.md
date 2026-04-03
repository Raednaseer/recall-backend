# Recall — RAG Chatbot Backend

> **Audience**: This document is written for the frontend/design team. It covers every API endpoint, auth flow, and data shape you need to design and build the client.

## Overview

Recall is a **Retrieval-Augmented Generation (RAG)** chatbot backend. Users upload documents (PDF/TXT), and the system chunks, embeds, and stores them in a vector database. Users can then ask questions, and the system retrieves relevant context from their documents to generate accurate answers via an LLM.

### Core Capabilities

| Capability | Description |
|---|---|
| **Document Upload** | Upload PDFs and text files, organized into named collections |
| **AI Chat** | Ask questions — answers are grounded in the user's uploaded documents |
| **Streaming Chat** | Real-time SSE streaming of LLM responses (token-by-token) |
| **Chat History** | Full conversation persistence with list, retrieve, and delete |
| **File Management** | List and delete uploaded files |
| **Authentication** | JWT-based register/login/refresh flow |

### Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI (Python 3.12) |
| Database | MongoDB Atlas |
| Vector Store | Qdrant Cloud |
| Cache / Rate Limiting | Redis |
| LLM | Groq (Qwen 3 32B) |
| Embeddings | Google Gemini Embedding 001 |

---

## Base URL

```
Production:  https://testapp-2fb1545c.fastapicloud.dev
Local:       http://localhost:8000
API Docs:    {base_url}/docs
```

---

## Authentication

All endpoints except `/health`, `/auth/register`, and `/auth/login` require a JWT Bearer token.

### Flow

```
1. Register or Login  →  receive access_token
2. Attach to all requests  →  Authorization: Bearer <token>
3. Token expires in 60 min  →  call /auth/refresh before expiry
```

### Headers (for all authenticated requests)

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

---

## API Reference

### Auth

#### `POST /auth/register`
Create a new account and receive a token.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword"
}
```

**Response `201`:**
```json
{
  "access_token": "eyJhbGci...",
  "token_type": "bearer"
}
```

**Errors:**
| Code | Meaning |
|------|---------|
| `409` | Email already registered |
| `422` | Invalid email format or missing fields |

---

#### `POST /auth/login`
Authenticate and receive a token.

**Request Body:** Same as register.

**Response `200`:**
```json
{
  "access_token": "eyJhbGci...",
  "token_type": "bearer"
}
```

**Errors:**
| Code | Meaning |
|------|---------|
| `401` | Invalid email or password |

---

#### `POST /auth/refresh` 🔒
Exchange a valid (non-expired) token for a fresh one. Use this to keep sessions alive without re-entering credentials.

**Request:** No body required — just the `Authorization` header.

**Response `200`:**
```json
{
  "access_token": "eyJhbGci...(new)...",
  "token_type": "bearer"
}
```

---

### Documents

#### `POST /rag/upload` 🔒
Upload a document for RAG processing.

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | File | ✅ | PDF or TXT file (max 10 MB) |
| `collection` | Query param | ❌ | Folder/group name (default: `"default"`) |

**Example:**
```
POST /rag/upload?collection=work
Content-Type: multipart/form-data
```

**Response `200`:**
```json
{
  "status": "uploaded",
  "file_id": "69cffe6ebda13c27d82941f6",
  "filename": "report.pdf",
  "collection": "work",
  "chunks": 44
}
```

**Errors:**
| Code | Meaning |
|------|---------|
| `413` | File too large (> 10 MB) |
| `415` | Unsupported file type (only PDF, TXT allowed) |
| `429` | Rate limit exceeded (5 uploads/min) |

---

#### `GET /rag/files` 🔒
List all uploaded files for the current user.

| Query Param | Type | Required | Description |
|-------------|------|----------|-------------|
| `collection` | string | ❌ | Filter by collection name |

**Response `200`:**
```json
{
  "files": [
    {
      "_id": "69cffe6ebda13c27d82941f6",
      "user_id": "69cff885a124f6a887f81bc8",
      "filename": "report.pdf",
      "content_type": "application/pdf",
      "collection": "work",
      "chunk_count": 44,
      "uploaded_at": "2026-04-03T18:00:00Z"
    }
  ],
  "count": 1
}
```

---

#### `DELETE /rag/files/{file_id}` 🔒
Delete a file and all its vector embeddings.

**Response `200`:**
```json
{
  "status": "deleted",
  "file_id": "69cffe6ebda13c27d82941f6",
  "filename": "report.pdf",
  "chunks_removed": 44
}
```

**Errors:**
| Code | Meaning |
|------|---------|
| `400` | Invalid file ID format |
| `403` | File belongs to another user |
| `404` | File not found |

---

### Chat

#### `POST /rag/chat` 🔒
Ask a question — receives a complete JSON response.

**Request Body:**
```json
{
  "query": "What are the key findings in the report?",
  "conversation_id": null,
  "collection": "default"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `query` | string | ✅ | — | The user's question |
| `conversation_id` | string \| null | ❌ | `null` | Pass to continue an existing conversation |
| `collection` | string | ❌ | `"default"` | Scope search to a specific collection |

**Response `200`:**
```json
{
  "answer": "The key findings indicate that...",
  "sources": [
    {
      "user_id": "69cff885a124f6a887f81bc8",
      "filename": "report.pdf",
      "collection": "work",
      "page": 3
    }
  ],
  "conversation_id": "69d00123abc456def7890123"
}
```

> **Design Note:** The first chat creates a new `conversation_id`. Pass it back on subsequent messages to build a multi-turn conversation thread.

**Errors:**
| Code | Meaning |
|------|---------|
| `429` | Rate limit exceeded (20 chats/min) |

---

#### `POST /rag/chat/stream` 🔒
Ask a question — receives real-time **Server-Sent Events (SSE)** stream.

**Request Body:** Same as `/rag/chat`.

**Response:** `text/event-stream` — each chunk arrives as an SSE event:

```
data: {"content":"The"}

data: {"content":" key"}

data: {"content":" findings"}

data: {"content":" indicate"}

data: {"content":" that..."}
```

> **Design Note:** This is the recommended endpoint for the chat UI. Use the [EventSource API](https://developer.mozilla.org/en-US/docs/Web/API/EventSource) or `fetch()` with a readable stream to consume it. Each event's `data` field contains a JSON object with a `content` string — concatenate them to build the full response.

**Frontend Implementation Hint:**
```javascript
// Using fetch for POST-based SSE (EventSource only supports GET)
const response = await fetch('/rag/chat/stream', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({ query, conversation_id, collection }),
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;

  const text = decoder.decode(value);
  // Parse SSE lines: "data: {\"content\":\"...\"}\n\n"
  const lines = text.split('\n').filter(l => l.startsWith('data: '));
  for (const line of lines) {
    const { content } = JSON.parse(line.slice(6));
    appendToUI(content); // render token-by-token
  }
}
```

---

### Chat History

#### `GET /history/` 🔒
List all conversations for the current user (newest first).

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `limit` | int | `20` | Max results (1–100) |
| `skip` | int | `0` | Offset for pagination |

**Response `200`:**
```json
{
  "conversations": [
    {
      "_id": "69d00123abc456def7890123",
      "user_id": "69cff885a124f6a887f81bc8",
      "title": "What are the key findings in the report?",
      "messages": [
        {
          "query": "What are the key findings in the report?",
          "answer": "The key findings indicate that...",
          "sources": [...],
          "timestamp": "2026-04-03T18:10:00Z"
        }
      ],
      "created_at": "2026-04-03T18:10:00Z",
      "updated_at": "2026-04-03T18:12:00Z"
    }
  ],
  "count": 1
}
```

> **Design Note:** The `title` field is auto-generated from the first 80 characters of the first query. The frontend may want to let users rename conversations — this is not yet supported on the backend.

---

#### `GET /history/{conversation_id}` 🔒
Retrieve a single conversation with all messages.

**Response `200`:** Same shape as a single item from the list above.

---

#### `DELETE /history/{conversation_id}` 🔒
Delete a conversation and all its messages.

**Response `200`:**
```json
{
  "status": "deleted",
  "conversation_id": "69d00123abc456def7890123"
}
```

---

### System

#### `GET /health`
Public endpoint — no auth required. Checks all backend services.

**Response `200`:**
```json
{
  "mongodb": "healthy",
  "redis": "healthy",
  "qdrant": "healthy",
  "status": "ok"
}
```

`status` will be `"degraded"` if any service is unhealthy.

---

## Key Design Considerations for the Frontend

### 1. Auth Flow
- Store the `access_token` in memory (not localStorage for security, or use httpOnly cookies if you add a BFF layer)
- Set a timer to call `/auth/refresh` before the 60-minute expiry
- On `401` response, redirect to login

### 2. Collections Model
- Collections are freeform strings — the user types whatever name they want (e.g., "Work", "School", "Research")
- The backend does not have a "list all collections" endpoint yet — derive the unique collection names from the `GET /rag/files` response
- Consider a sidebar with collection names as folders

### 3. Chat UX
- Use the **streaming endpoint** (`/chat/stream`) for the primary chat interface
- Show a typing indicator / token-by-token text rendering as chunks arrive
- After the stream ends, the response is automatically saved to chat history
- Pass `conversation_id` on follow-up messages to maintain context
- Without a `conversation_id`, a new conversation thread is created

### 4. File Upload UX
- Only PDF and TXT files are accepted (max 10 MB)
- Show a progress indicator — large PDFs may take 5–10 seconds to process
- After upload, the file appears in `GET /rag/files` and is immediately searchable via chat
- Display `chunk_count` as an indicator of document size

### 5. Rate Limiting
- Chat: **20 requests/min** per user
- Upload: **5 requests/min** per user
- On `429`, display the retry message from the `detail` field (includes seconds until reset)

### 6. Error Handling
All API errors return a consistent JSON shape:
```json
{
  "detail": "Human-readable error message"
}
```
For validation errors (`422`), the shape is:
```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "query"],
      "msg": "Field required"
    }
  ]
}
```

### 7. CORS
CORS is enabled for all origins by default. The frontend can be hosted on any domain.

---

## Data Flow Diagram

```
┌─────────┐     Register/Login       ┌──────────┐
│         │ ──────────────────────►  │          │
│  Client │     JWT Token            │  Auth    │
│  (SPA)  │ ◄──────────────────────  │  Service │
│         │                          └──────────┘
│         │
│         │     Upload (PDF/TXT)     ┌──────────┐     Chunks      ┌─────────┐
│         │ ──────────────────────►  │  RAG     │ ─────────────►  │ Qdrant  │
│         │     file_id + metadata   │  Service │     Vectors     │ (Cloud) │
│         │ ◄──────────────────────  │          │ ◄─────────────  │         │
│         │                          │          │                 └─────────┘
│         │     Chat Query           │          │     Context
│         │ ──────────────────────►  │          │ ─────────────►  ┌─────────┐
│         │     SSE Stream / JSON    │          │     LLM Answer  │  Groq   │
│         │ ◄──────────────────────  │          │ ◄─────────────  │  (LLM)  │
│         │                          └──────────┘                 └─────────┘
│         │                               │
│         │     History CRUD              ▼
│         │ ◄────────────────────►  ┌──────────┐
│         │                         │ MongoDB  │
└─────────┘                         └──────────┘
```

---

## API Endpoints Summary

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/auth/register` | ❌ | Create account |
| `POST` | `/auth/login` | ❌ | Login |
| `POST` | `/auth/refresh` | 🔒 | Refresh token |
| `POST` | `/rag/upload` | 🔒 | Upload document |
| `GET` | `/rag/files` | 🔒 | List files |
| `DELETE` | `/rag/files/{file_id}` | 🔒 | Delete file |
| `POST` | `/rag/chat` | 🔒 | Chat (JSON response) |
| `POST` | `/rag/chat/stream` | 🔒 | Chat (SSE stream) |
| `GET` | `/history/` | 🔒 | List conversations |
| `GET` | `/history/{id}` | 🔒 | Get conversation |
| `DELETE` | `/history/{id}` | 🔒 | Delete conversation |
| `GET` | `/health` | ❌ | Service health check |
