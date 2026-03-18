"""auth_simple.py - Simple API key authentication

No OAuth, no external dependencies. Just API keys.
"""
import secrets
from fastapi import HTTPException, Header
from typing import Optional

from simple_db import SimpleMemoryDB


class SimpleAuth:
    """Simple API key based authentication."""

    def __init__(self, db: SimpleMemoryDB):
        self.db = db

    def generate_api_key(self, user_id: str) -> str:
        """
        Generate a new API key for a user.

        Args:
            user_id: User identifier (email, username, etc.)

        Returns:
            API key string
        """
        # Generate secure random key
        api_key = f"mem_{secrets.token_urlsafe(32)}"

        # Store in database
        success = self.db.create_api_key(api_key, user_id)

        if not success:
            raise ValueError("Failed to create API key (may already exist)")

        return api_key

    def verify_api_key(self, api_key: str) -> str:
        """
        Verify API key and return user_id.

        Args:
            api_key: API key to verify

        Returns:
            user_id if valid

        Raises:
            HTTPException if invalid
        """
        user_id = self.db.verify_api_key(api_key)

        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="Invalid API key"
            )

        return user_id


# FastAPI dependency
def get_current_user(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> str:
    """
    FastAPI dependency to get current user from API key header.

    Usage:
        @app.get("/memories")
        def list_memories(user_id: str = Depends(get_current_user)):
            ...
    """
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing X-API-Key header"
        )

    # Global db instance will be set by app
    from app_local import db, auth

    return auth.verify_api_key(x_api_key)
