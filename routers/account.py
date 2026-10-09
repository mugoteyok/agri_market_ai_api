
import os

from fastapi import APIRouter, Depends, HTTPException
from supabase import Client, create_client

from auth import get_authenticated_user

router = APIRouter(prefix="/api/account", tags=["Account"])


def get_admin_client() -> Client:
    """Create a server-side Supabase admin client."""
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


def has_user_records(
    admin_client: Client,
    table: str,
    column: str,
    user_id: str,
) -> bool:
    """Check whether a protected table contains records for this user."""
    response = (
        admin_client.table(table)
        .select(column)
        .eq(column, user_id)
        .limit(1)
        .execute()
    )
    return bool(response.data)


def has_nonzero_wallet(
    admin_client: Client,
    column: str,
    user_id: str,
) -> bool:
    """Prevent deletion when a wallet contains a nonzero balance."""
    response = (
        admin_client.table("wallets")
        .select("id")
        .eq(column, user_id)
        .neq("balance", 0)
        .limit(1)
        .execute()
    )
    return bool(response.data)


def check_deletion_safety(
    admin_client: Client,
    user_id: str,
) -> None:
    """
    Fail closed when records need a dedicated retention workflow.
    No records are changed by these checks.
    """
    protected_checks = [
        # Marketplace and financial records
        ("orders", "buyer_id"),
        ("orders", "farmer_id"),
        ("orders", "seller_id"),
        ("transactions", "farmer_id"),
        ("transactions", "seller_id"),
        ("withdrawals", "farmer_id"),
        ("withdrawals", "seller_id"),

        # Subscriptions and products
        ("subscriptions", "supplier_id"),
        ("subscription_payments", "supplier_id"),
        ("products", "farmer_id"),
        ("products", "seller_id"),

        # Business administration and ownership
        ("business_accounts", "approved_by"),
        ("business_portal_admins", "created_by"),
        ("business_profiles", "supplier_id"),

        # User activity and support records
        ("disease_history", "user_id"),
        ("notifications", "user_id"),
        ("support_agents", "user_id"),
        ("support_messages", "sender_id"),
        ("support_tickets", "user_id"),
    ]

    for table, column in protected_checks:
        if has_user_records(admin_client, table, column, user_id):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Account deletion requires additional review because "
                    "this account is linked to marketplace, financial, "
                    "business, support, or subscription records. "
                    "Please contact support."
                ),
            )

    # Check both farmer and seller wallet associations.
    for column in ("farmer_id", "seller_id"):
        if has_nonzero_wallet(admin_client, column, user_id):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Account deletion is unavailable while a wallet has "
                    "a nonzero balance. Resolve the balance first."
                ),
            )


@router.delete("/delete")
async def delete_account(
    user=Depends(get_authenticated_user),
):
    """Delete only the authenticated user's account after safety checks."""
    user_id = getattr(user, "id", None)

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Unable to identify the authenticated account.",
        )

    admin_client = get_admin_client()

    try:
        # All checks run before the permanent Auth deletion.
        # If a check fails or cannot complete, do not delete the account.
        check_deletion_safety(admin_client, str(user_id))

        result = admin_client.auth.admin.delete_user(str(user_id))

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
        # Do not log tokens, personal data, or secret values.
        print("Account deletion failed:", type(exc).__name__)

        raise HTTPException(
            status_code=500,
            detail=(
                "Account deletion could not be completed. "
                "No successful deletion was confirmed."
            ),
        )
