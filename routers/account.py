
import os

from fastapi import APIRouter, Depends, HTTPException
from supabase import create_client, Client

from auth import get_authenticated_user

router = APIRouter(prefix="/api/account", tags=["Account"])


def get_admin_client() -> Client:
    """
    Create a server-side Supabase admin client.
    Never expose the service-role key to the Flutter app.
    """
    supabase_url = os.getenv("SUPABASE_URL")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not service_role_key:
        raise HTTPException(
            status_code=503,
            detail="Account deletion is not configured.",
        )

    try:
        return create_client(supabase_url, service_role_key)
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Account deletion service is unavailable.",
        )


@router.delete("/delete")
async def delete_account(
    user=Depends(get_authenticated_user),
):
    """
    Delete the authenticated user's Supabase Auth account.
    The target user ID comes only from the verified access token.
    """
    user_id = getattr(user, "id", None)

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Unable to identify the authenticated account.",
        )

    admin_client = get_admin_client()

    try:
        result = admin_client.auth.admin.delete_user(user_id)

        # Supabase admin deletion normally raises an exception on failure.
        # Do not report success if the call explicitly reports an error.
        if getattr(result, "error", None):
            raise HTTPException(
                status_code=500,
                detail="Account deletion could not be completed.",
            )

        return {
            "success": True,
            "message": "Account deleted successfully.",
        }

    except HTTPException:
        raise

    except Exception as exc:
        # Log only the exception type; do not log tokens or secret values.
        print("Account deletion failed:", type(exc).__name__)

        raise HTTPException(
            status_code=500,
            detail="Account deletion could not be completed. Please contact support.",
        )
