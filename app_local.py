"""app_local.py - Simple local memory API

A lightweight, self-hosted memory API with:
- Text-based memory storage
- Semantic vector search
- Optional Llama AI enhancements
- API key authentication
- SQLite storage
"""
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
import os

from simple_db import SimpleMemoryDB
from auth_simple import SimpleAuth, get_current_user
from llama_helpers import is_llama_available, enhance_memory

# Initialize
app = FastAPI(
    title="Simple Memory API",
    description="Self-hosted memory storage with semantic search",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database and auth
db = SimpleMemoryDB(db_path=os.getenv("DB_PATH", "db/memories.db"))
auth = SimpleAuth(db)

# Pydantic models
class MemoryCreate(BaseModel):
    content: str = Field(..., description="Memory content text")
    metadata: Optional[Dict] = Field(None, description="Optional metadata")
    enhance: bool = Field(False, description="Use Llama to enhance with summary/keywords")


class MemoryResponse(BaseModel):
    id: int
    content: str
    metadata: Optional[Dict]
    created_at: int
    updated_at: int
    score: Optional[float] = None


class MemorySearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    top_k: int = Field(5, ge=1, le=20, description="Number of results")


class MemoryLinkCreate(BaseModel):
    from_memory_id: int = Field(..., description="Source memory ID")
    to_memory_id: int = Field(..., description="Target memory ID")
    link_type: Optional[str] = Field(None, description="Link type (e.g., 'related', 'caused_by', 'leads_to')")


class APIKeyCreate(BaseModel):
    user_id: str = Field(..., description="User identifier (email, username, etc.)")


class APIKeyResponse(BaseModel):
    api_key: str
    user_id: str
    message: str


# ===== Public Endpoints =====

@app.get("/")
def root():
    """API information."""
    llama_status = "available" if is_llama_available() else "not available"
    return {
        "service": "Simple Memory API",
        "version": "1.0.0",
        "docs": "/docs",
        "llama": llama_status
    }


@app.get("/health")
def health():
    """Health check."""
    return {"status": "healthy"}


@app.post("/api-keys", response_model=APIKeyResponse)
def create_api_key(request: APIKeyCreate):
    """
    Create a new API key.

    This endpoint is unprotected to allow initial setup.
    In production, you should protect this or run it via CLI.
    """
    try:
        api_key = auth.generate_api_key(request.user_id)
        return {
            "api_key": api_key,
            "user_id": request.user_id,
            "message": "Save this API key securely. Use it in X-API-Key header for all requests."
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ===== Protected Endpoints (require X-API-Key header) =====

@app.post("/memories", response_model=MemoryResponse)
def create_memory(
    request: MemoryCreate,
    user_id: str = Depends(get_current_user)
):
    """Create a new memory."""
    metadata = request.metadata or {}

    # Optional Llama enhancement
    if request.enhance and is_llama_available():
        ai_metadata = enhance_memory(request.content)
        metadata.update(ai_metadata)

    memory_id = db.create_memory(user_id, request.content, metadata)
    memory = db.get_memory(memory_id, user_id)

    return MemoryResponse(**memory)


@app.get("/memories", response_model=List[MemoryResponse])
def list_memories(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user_id: str = Depends(get_current_user)
):
    """List all memories for the current user."""
    memories = db.list_memories(user_id, limit, offset)
    return [MemoryResponse(**m) for m in memories]


@app.get("/memories/{memory_id}", response_model=MemoryResponse)
def get_memory(
    memory_id: int,
    user_id: str = Depends(get_current_user)
):
    """Get a specific memory by ID."""
    memory = db.get_memory(memory_id, user_id)

    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    return MemoryResponse(**memory)


@app.delete("/memories/{memory_id}")
def delete_memory(
    memory_id: int,
    user_id: str = Depends(get_current_user)
):
    """Delete a memory."""
    success = db.delete_memory(memory_id, user_id)

    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")

    return {"success": True, "memory_id": memory_id}


@app.post("/memories/search", response_model=List[MemoryResponse])
def search_memories(
    request: MemorySearchRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Search memories using semantic vector similarity.

    Combines FTS keyword matching with vector embeddings for best results.
    """
    results = db.search_memories(user_id, request.query, request.top_k)
    return [MemoryResponse(**r) for r in results]


@app.get("/stats")
def get_stats(user_id: str = Depends(get_current_user)):
    """Get statistics for the current user."""
    total_memories = db.count_memories(user_id)

    return {
        "user_id": user_id,
        "total_memories": total_memories,
        "llama_available": is_llama_available()
    }


# ===== Graph Endpoints =====

@app.post("/graph/links")
def create_link(
    request: MemoryLinkCreate,
    user_id: str = Depends(get_current_user)
):
    """Create a link between two memories."""
    success = db.create_link(
        request.from_memory_id,
        request.to_memory_id,
        user_id,
        request.link_type
    )

    if not success:
        raise HTTPException(
            status_code=400,
            detail="Failed to create link. Check that both memories exist and link doesn't already exist."
        )

    return {
        "success": True,
        "from_memory_id": request.from_memory_id,
        "to_memory_id": request.to_memory_id,
        "link_type": request.link_type
    }


@app.get("/graph/links/{memory_id}")
def get_linked_memories(
    memory_id: int,
    direction: str = Query("both", regex="^(both|outgoing|incoming)$"),
    user_id: str = Depends(get_current_user)
):
    """
    Get memories linked to a given memory.

    - direction: "both" (default), "outgoing", or "incoming"
    """
    # Verify memory exists
    memory = db.get_memory(memory_id, user_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    links = db.get_linked_memories(memory_id, user_id, direction)

    return {
        "memory_id": memory_id,
        "outgoing": links["outgoing"],
        "incoming": links["incoming"]
    }


@app.delete("/graph/links")
def delete_link(
    from_memory_id: int = Query(...),
    to_memory_id: int = Query(...),
    user_id: str = Depends(get_current_user)
):
    """Delete a link between two memories."""
    success = db.delete_link(from_memory_id, to_memory_id, user_id)

    if not success:
        raise HTTPException(status_code=404, detail="Link not found")

    return {
        "success": True,
        "from_memory_id": from_memory_id,
        "to_memory_id": to_memory_id
    }


@app.get("/graph/{memory_id}")
def get_memory_graph(
    memory_id: int,
    depth: int = Query(1, ge=1, le=3, description="Graph traversal depth (1-3)"),
    user_id: str = Depends(get_current_user)
):
    """
    Get a subgraph around a memory.

    Returns all memories and links within N hops of the center memory.
    Useful for visualizing memory connections.
    """
    graph = db.get_memory_graph(memory_id, user_id, depth)

    if not graph:
        raise HTTPException(status_code=404, detail="Memory not found")

    return graph


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
