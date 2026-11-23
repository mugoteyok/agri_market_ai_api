"""Safe account deletion for the Agri AI Assist primary Supabase project.

Deletion is deliberately fail-closed. Records that can represent shared
marketplace, financial, support, business-ownership, or machinery activity
must be transferred or handled separately before Auth deletion is allowed.
"""

import os
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from supabase import Client, create_client

from auth import get_authenticated_user

router = APIRouter(prefix="/api/account", tags=["Account"])

# This endpoint is intentionally pinned to the Supabase project audited for
# account deletion. Do not silently run it against the legacy project.
PRIMARY_SUPABASE_PROJECT_REF = "xemhoptmlaxahdhfevuc"
PRIMARY_SUPABASE_HOST = f"{PRIMARY_SUPABASE_PROJECT_REF}.supabase.co"

# Buckets found in the primary project's Storage audit. The audit confirmed
# that user-owned objects are stored under a first-level folder named by the
# Auth UUID. Only objects below the authenticated user's folder are removed.
USER_STORAGE_BUCKETS = (
    "avatars",
    "coffee-dataset",
    "disease-scans",
    "machinery-media",
    "product-images",
    "product-videos",
)

STORAGE_LIST_PAGE_SIZE = 100
STORAGE_REMOVE_BATCH_SIZE = 1000


# These records can involve other users or represent financial history. They
# are not deleted automatically. The owner must transfer or resolve them first.
BLOCKING_USER_RECORDS = (
    ("business_accounts", "owner_user_id", "business account ownership"),
    ("orders", "buyer_id", "marketplace orders"),
    ("orders", "farmer_id", "marketplace orders"),
    ("orders", "seller_id", "marketplace orders"),
    ("products", "farmer_id", "product listings"),
    ("products", "seller_id", "product listings"),
    ("marketplace_transactions", "buyer_id", "marketplace transaction history"),
    ("marketplace_transactions", "seller_id", "marketplace transaction history"),
    ("marketplace_payouts", "seller_id", "payout history"),
    ("marketplace_refunds", "buyer_id", "refund history"),
    ("marketplace_refunds", "seller_id", "refund history"),
    ("product_promotions", "seller_id", "promotion/payment history"),
    ("transactions", "farmer_id", "wallet transaction history"),
    ("transactions", "seller_id", "wallet transaction history"),
    ("withdrawals", "farmer_id", "withdrawal history"),
    ("withdrawals", "seller_id", "withdrawal history"),
    ("subscriptions", "supplier_id", "subscription history"),
    ("subscription_payments", "supplier_id", "subscription payment history"),
    # Deleting a listing or inquiry can cascade to inquiries/replies belonging
    # to other people. Require these records to be transferred or resolved.
    ("machinery_listings", "owner_id", "machinery listings"),
    ("machinery_inquiries", "owner_id", "machinery inquiries"),
    ("machinery_inquiries", "renter_id", "machinery inquiries"),
    ("machinery_inquiry_replies", "sender_id", "machinery inquiry replies"),
    # A support ticket owns its entire message thread through a CASCADE FK.
    # Keep the ticket/thread intact until it is handled by the support process.
    ("support_tickets", "user_id", "support tickets"),
    # A user may have sent messages in another user's ticket. Because sender_id
    # cascades to auth.users, block deletion rather than erase shared support history.
    ("support_messages", "sender_id", "support conversation messages"),
    ("support_agents", "user_id", "support-agent access"),
)


class AccountDeletionBlocked(Exception):
    """Internal marker for a preflight condition that requires user action."""


def get_admin_client() -> Client:
    """Create a trusted service-role client for the audited primary project."""
    supabase_url = os.getenv("SUPABASE_URL")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not service_role_key:
        raise HTTPException(
            status_code=503,
            detail="Account deletion is not configured.",
        )

    parsed_url = urlparse(supabase_url)
    if parsed_url.scheme != "https" or parsed_url.hostname != PRIMARY_SUPABASE_HOST:
        raise HTTPException(
            status_code=503,
            detail="Account deletion is not configured for the approved Supabase project.",
        )

    try:
        return create_client(supabase_url.rstrip("/"), service_role_key)
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
    """Return whether a table contains at least one row for this Auth user."""
    response = (
        admin_client.table(table)
        .select(column)
        .eq(column, user_id)
        .limit(1)
        .execute()
    )
    return bool(response.data)


def _check_wallet_balances(admin_client: Client, user_id: str) -> None:
    """Only zero-balance wallets exclusively linked to this user may be removed."""
    for column in ("farmer_id", "seller_id"):
        response = (
            admin_client.table("wallets")
            .select("balance,farmer_id,seller_id")
            .eq(column, user_id)
            .limit(1000)
            .execute()
        )
        for wallet in response.data or []:
            # A wallet row must not simultaneously identify a different user.
            other_column = "seller_id" if column == "farmer_id" else "farmer_id"
            other_user_id = wallet.get(other_column)
            if other_user_id is not None and str(other_user_id) != user_id:
                raise AccountDeletionBlocked(
                    "A wallet contains a conflicting second user reference. "
                    "Resolve its ownership before deletion."
                )

            # A NULL balance is unknown, not proof of a zero balance.
            balance = wallet.get("balance")
            try:
                is_zero = balance is not None and float(balance) == 0.0
            except (TypeError, ValueError):
                is_zero = False
            if not is_zero:
                raise AccountDeletionBlocked(
                    "A wallet has a nonzero or unknown balance. Resolve it before deletion."
                )


def check_deletion_safety(admin_client: Client, user_id: str) -> None:
    """Fail closed before changing Storage or database records."""
    blockers: list[str] = []

    for table, column, label in BLOCKING_USER_RECORDS:
        if has_user_records(admin_client, table, column, user_id):
            blockers.append(label)

    try:
        _check_wallet_balances(admin_client, user_id)
    except AccountDeletionBlocked as exc:
        blockers.append(str(exc))

    # A creator reference can be cleared because created_by is nullable. The
    # administrator row itself cascades with user_id. But deleting the sole
    # portal administrator would leave the business portal without an admin.
    if has_user_records(admin_client, "business_portal_admins", "user_id", user_id):
        has_other_admin = (
            admin_client.table("business_portal_admins")
            .select("user_id")
            .neq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not has_other_admin.data:
            blockers.append(
                "last business portal administrator (appoint another administrator first)"
            )

    if blockers:
        labels = "; ".join(sorted(set(blockers)))
        raise HTTPException(
            status_code=409,
            detail=(
                "Account deletion is blocked until these records are transferred, "
                "resolved, or retained through the appropriate workflow: "
                f"{labels}. No account or Storage data has been deleted."
            ),
        )


def _list_user_storage_paths(bucket: Any, user_id: str) -> list[str]:
    """Recursively list files strictly below one user's Storage folder."""
    pending_folders = [user_id]
    visited_folders: set[str] = set()
    object_paths: list[str] = []

    while pending_folders:
        folder = pending_folders.pop()
        if folder in visited_folders:
            continue
        visited_folders.add(folder)

        offset = 0
        while True:
            entries = bucket.list(
                folder,
                {"limit": STORAGE_LIST_PAGE_SIZE, "offset": offset},
            )
            if not isinstance(entries, list):
                raise RuntimeError("Storage returned an unexpected listing response.")
            if not entries:
                break

            for entry in entries:
                if not isinstance(entry, dict):
                    raise RuntimeError("Storage returned an invalid object entry.")

                name = entry.get("name")
                if (
                    not isinstance(name, str)
                    or not name
                    or name in {".", ".."}
                    or "/" in name
                    or "\\" in name
                ):
                    raise RuntimeError("Storage returned an unsafe object path.")

                object_path = f"{folder}/{name}"
                if not object_path.startswith(f"{user_id}/"):
                    raise RuntimeError("Refusing to remove an object outside the user's folder.")

                # Supabase Storage represents folders with a null id; files
                # have an object id. This avoids mistaking nested folders for files.
                if entry.get("id") is None:
                    pending_folders.append(object_path)
                else:
                    object_paths.append(object_path)

            if len(entries) < STORAGE_LIST_PAGE_SIZE:
                break
            offset += len(entries)

    return object_paths


def _build_storage_cleanup_plan(admin_client: Client, user_id: str) -> dict[str, list[str]]:
    """List every bucket before deleting anything, so missing buckets fail early."""
    plan: dict[str, list[str]] = {}
    for bucket_name in USER_STORAGE_BUCKETS:
        bucket = admin_client.storage.from_(bucket_name)
        plan[bucket_name] = _list_user_storage_paths(bucket, user_id)
    return plan


def _remove_user_storage_objects(
    admin_client: Client,
    user_id: str,
    cleanup_plan: dict[str, list[str]],
) -> int:
    """Remove the user's files through Storage API batches and verify the result."""
    removed_count = 0

    for bucket_name, paths in cleanup_plan.items():
        bucket = admin_client.storage.from_(bucket_name)
        for start in range(0, len(paths), STORAGE_REMOVE_BATCH_SIZE):
            batch = paths[start : start + STORAGE_REMOVE_BATCH_SIZE]
            bucket.remove(batch)
            removed_count += len(batch)

        remaining = _list_user_storage_paths(bucket, user_id)
        if remaining:
            raise RuntimeError(
                f"Storage cleanup verification failed for bucket {bucket_name}."
            )

    return removed_count


def _clear_nullable_user_references(admin_client: Client, user_id: str) -> None:
    """Preserve business/audit rows while clearing nullable Auth identity links."""
    # Keep the approved business account and its approval date/notes. Only the
    # nullable approver FK is cleared so profile deletion cannot cascade/block it.
    (
        admin_client.table("business_accounts")
        .update({"approved_by": None})
        .eq("approved_by", user_id)
        .execute()
    )

    # created_by is nullable. The user's own portal-admin row is handled by its
    # user_id CASCADE, or deletion is blocked above if they are the last admin.
    (
        admin_client.table("business_portal_admins")
        .update({"created_by": None})
        .eq("created_by", user_id)
        .execute()
    )

    # Retain financial audit events while removing nullable direct user IDs.
    for column in ("actor_id", "approved_by"):
        (
            admin_client.table("financial_audit_log")
            .update({column: None})
            .eq(column, user_id)
            .execute()
        )

    # Verify both NO ACTION foreign-key references were actually cleared.
    for table, column in (
        ("business_accounts", "approved_by"),
        ("business_portal_admins", "created_by"),
    ):
        if has_user_records(admin_client, table, column, user_id):
            raise RuntimeError(
                f"Could not clear the {table}.{column} reference before Auth deletion."
            )


def _delete_unconstrained_user_rows(admin_client: Client, user_id: str) -> None:
    """Remove user-owned rows whose user ID has no Auth FK and would otherwise remain."""
    # These columns are nullable and are not protected by an Auth FK in the
    # audited schema. Delete by exact Auth UUID only; never use broad predicates.
    (
        admin_client.table("farmers")
        .delete()
        .eq("user_id", user_id)
        .execute()
    )
    (
        admin_client.table("wallets")
        .delete()
        .eq("farmer_id", user_id)
        .execute()
    )
    (
        admin_client.table("wallets")
        .delete()
        .eq("seller_id", user_id)
        .execute()
    )


@router.delete("/delete")
async def delete_account(user=Depends(get_authenticated_user)):
    """Delete only the authenticated user's account after fail-closed cleanup."""
    user_id = getattr(user, "id", None)
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Unable to identify the authenticated account.",
        )

    user_id = str(user_id)
    admin_client = get_admin_client()

    try:
        # No side effects before the complete database and Storage preflight.
        check_deletion_safety(admin_client, user_id)
        storage_plan = _build_storage_cleanup_plan(admin_client, user_id)

        # Remove objects through Storage API before deleting Auth; Supabase
        # refuses Auth deletion while the user still owns Storage objects.
        _remove_user_storage_objects(admin_client, user_id, storage_plan)

        # Resolve nullable NO ACTION FKs and remove exact-UUID rows that do not
        # cascade from auth.users. These operations are retry-safe.
        _clear_nullable_user_references(admin_client, user_id)
        _delete_unconstrained_user_rows(admin_client, user_id)

        # Auth deletion runs last. Remaining CASCADE relationships are limited
        # to the user's own rows because shared/high-risk relationships were
        # rejected in the preflight checks above.
        result = admin_client.auth.admin.delete_user(user_id)
        if getattr(result, "error", None):
            raise RuntimeError("Supabase Auth did not confirm user deletion.")

        return {
            "success": True,
            "message": "Account and eligible user-owned data deleted successfully.",
        }

    except HTTPException:
        raise
    except Exception as exc:
        # Do not log JWTs, email addresses, storage paths, or secret values.
        print("Account deletion failed:", type(exc).__name__)
        raise HTTPException(
            status_code=500,
            detail=(
                "Account deletion could not be confirmed. The request may have "
                "completed only part of its cleanup; contact support before retrying."
            ),
        )
