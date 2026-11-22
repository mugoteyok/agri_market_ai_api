from dataclasses import dataclass
from typing import Any

from fastapi import Header, HTTPException
from supabase import Client

from database import create_user_client, supabase


@dataclass(frozen=True)
class AuthenticatedContext:
    """Verified user identity and an isolated JWT-authenticated DB client."""
    user: Any
    db: Client


async def _verify_authorization_header(authorization: str | None):
    """Validate the Bearer token and return the verified user and token."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authentication required.")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header.")

    access_token = authorization.replace("Bearer ", "", 1).strip()
    if not access_token:
        raise HTTPException(status_code=401, detail="Authentication token is missing.")

    try:
        response = supabase.auth.get_user(access_token)
        user = response.user
        if not user:
            raise HTTPException(status_code=401, detail="Invalid or expired authentication token.")
        return user, access_token
    except HTTPException:
        raise
    except Exception as e:
        print("AUTHENTICATION ERROR:", str(e))
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token.")


async def get_authenticated_user(authorization: str | None = Header(default=None)):
    """Existing dependency, retained for compatibility with other routes."""
    user, _ = await _verify_authorization_header(authorization)
    return user


async def get_authenticated_context(
    authorization: str | None = Header(default=None),
) -> AuthenticatedContext:
    """Authenticate a user and create a request-scoped JWT database client."""
    user, access_token = await _verify_authorization_header(authorization)
    try:
        user_db = create_user_client(access_token)
    except Exception as e:
        print("CUSTOMER DATABASE CLIENT ERROR:", str(e))
        raise HTTPException(
            status_code=503,
            detail="Unable to initialize authenticated database access.",
        )
    return AuthenticatedContext(user=user, db=user_db)
