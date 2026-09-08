from fastapi import Header, HTTPException
from database import supabase


async def get_authenticated_user(
    authorization: str | None = Header(default=None),
):
    # ============================================================
    # CHECK AUTHORIZATION HEADER
    # ============================================================

    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
        )

    # ============================================================
    # CHECK BEARER TOKEN
    # ============================================================

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header.",
        )

    access_token = authorization.replace(
        "Bearer ",
        "",
        1,
    ).strip()

    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="Authentication token is missing.",
        )

    # ============================================================
    # VERIFY TOKEN WITH SUPABASE
    # ============================================================

    try:
        response = supabase.auth.get_user(
            access_token
        )

        user = response.user

        if not user:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired authentication token.",
            )

        return user

    except HTTPException:
        raise

    except Exception as e:
        print(
            "AUTHENTICATION ERROR:",
            str(e),
        )

        raise HTTPException(
            status_code=401,
            detail="Invalid or expired authentication token.",
        )
