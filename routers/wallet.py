
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from database import supabase
from auth import get_authenticated_user
from schemas.wallet import (
    WalletCreate,
    WalletEarning,
    WithdrawalCreate,
)
from services.mtn_service import (
    transfer_money,
    get_transfer_status,
)

router = APIRouter()


# ============================================================
# SHARED HELPERS
# ============================================================

ALLOWED_SELLER_TYPES = {"farmer", "supplier"}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def normalize_uganda_mobile_number(value: str) -> str:
    """Normalize a Ugandan mobile number to 2567XXXXXXXX."""

    if not isinstance(value, str):
        raise HTTPException(
            status_code=400,
            detail="Enter a valid Ugandan Mobile Money number.",
        )

    phone = re.sub(r"[\s\-()+]", "", value.strip())

    if phone.startswith("0"):
        phone = "256" + phone[1:]
    elif phone.startswith("7") and len(phone) == 9:
        phone = "256" + phone

    if (
        not phone.isdigit()
        or len(phone) != 12
        or not phone.startswith("2567")
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Enter a valid Ugandan mobile number, "
                "for example 07XXXXXXXX or 2567XXXXXXXX."
            ),
        )

    return phone


def mask_mobile_number(value: str | None) -> str | None:
    """Return only the last four digits of a saved number."""

    if not value:
        return None

    digits = re.sub(r"\D", "", value)
    return f"****{digits[-4:]}" if len(digits) >= 4 else "****"


def get_profile(user_id: str):
    response = (
        supabase.table("profiles")
        .select("id, role, mobile_money_number")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    return response.data


def get_wallet_record(seller_id: str, seller_type: str):
    response = (
        supabase.table("wallets")
        .select("*")
        .eq("seller_id", seller_id)
        .eq("seller_type", seller_type)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def ensure_wallet(seller_id: str, seller_type: str):
    """Find or create the authenticated user's seller wallet."""

    wallet = get_wallet_record(seller_id, seller_type)
    if wallet:
        return wallet

    wallet_data = {
        "farmer_id": seller_id if seller_type == "farmer" else None,
        "seller_id": seller_id,
        "seller_type": seller_type,
        "balance": 0,
        "currency": "UGX",
        "updated_at": utc_now(),
    }

    response = supabase.table("wallets").insert(wallet_data).execute()

    if not response.data:
        raise HTTPException(
            status_code=500,
            detail="Failed to create wallet.",
        )

    return response.data[0]


def require_seller(user, requested_seller_id: str, requested_type: str | None = None):
    """Validate wallet ownership and derive the role from profiles."""

    user_id = str(user.id)

    if user_id != str(requested_seller_id):
        raise HTTPException(
            status_code=403,
            detail="You can only access your own wallet.",
        )

    profile = get_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Seller profile not found.")

    role = (profile.get("role") or "").strip().lower()

    if role not in ALLOWED_SELLER_TYPES:
        raise HTTPException(
            status_code=403,
            detail="Only farmers and suppliers can access seller wallets.",
        )

    if requested_type and requested_type.lower() != role:
        raise HTTPException(
            status_code=403,
            detail="The requested seller type does not match your account.",
        )

    return role, profile


def wallet_for_api(wallet: dict) -> dict:
    """Do not expose a supplier's full receiving number in wallet responses."""

    result = dict(wallet)
    number = result.get("mobile_money_number")
    result["has_mobile_money_number"] = bool(number)
    result["mobile_money_number"] = mask_mobile_number(number)
    return result


# ============================================================
# GET FARMER WALLET
# GET /api/marketplace/wallet/{farmer_id}
# ============================================================

@router.get("/wallet/{farmer_id}")
async def get_wallet(
    farmer_id: str,
    user=Depends(get_authenticated_user),
):
    role, _ = require_seller(user, farmer_id)

    if role != "farmer":
        raise HTTPException(
            status_code=403,
            detail="This endpoint is for farmer wallets.",
        )

    wallet = ensure_wallet(str(user.id), "farmer")
    return wallet_for_api(wallet)


# ============================================================
# GET SELLER WALLET
# GET /api/marketplace/wallet/seller/{seller_id}
# ============================================================

@router.get("/wallet/seller/{seller_id}")
async def get_seller_wallet(
    seller_id: str,
    seller_type: str | None = None,
    user=Depends(get_authenticated_user),
):
    role, _ = require_seller(user, seller_id, seller_type)

    wallet = get_wallet_record(str(user.id), role)

    if not wallet:
        raise HTTPException(
            status_code=404,
            detail=f"{role.capitalize()} wallet not found.",
        )

    return wallet_for_api(wallet)


# ============================================================
# CREATE FARMER WALLET
# POST /api/marketplace/wallet/create
# ============================================================

@router.post("/wallet/create")
async def create_wallet(
    wallet: WalletCreate,
    user=Depends(get_authenticated_user),
):
    role, _ = require_seller(user, wallet.farmer_id)

    if role != "farmer":
        raise HTTPException(
            status_code=403,
            detail="This endpoint is for farmer wallets.",
        )

    existing = get_wallet_record(str(user.id), "farmer")
    if existing:
        return {
            "message": "Wallet already exists",
            "wallet": existing,
        }

    created = ensure_wallet(str(user.id), "farmer")
    return {
        "message": "Wallet created successfully",
        "wallet": created,
    }


# ============================================================
# CREATE SELLER WALLET
# POST /api/marketplace/wallet/seller/create
# ============================================================

@router.post("/wallet/seller/create")
async def create_seller_wallet(
    seller_id: str,
    seller_type: str,
    user=Depends(get_authenticated_user),
):
    seller_type = seller_type.strip().lower()
    role, _ = require_seller(user, seller_id, seller_type)

    if role not in ALLOWED_SELLER_TYPES:
        raise HTTPException(status_code=400, detail="Invalid seller type.")

    existing = get_wallet_record(str(user.id), role)
    if existing:
        return {
            "message": "Seller wallet already exists",
            "wallet": wallet_for_api(existing),
        }

    wallet = ensure_wallet(str(user.id), role)
    return {
        "message": "Seller wallet created successfully",
        "wallet": wallet_for_api(wallet),
    }


# ============================================================
# SUPPLIER RECEIVING NUMBER
#
# PUT /api/marketplace/wallet/seller/receiving-number
# Body: {"mobile_money_number": "07XXXXXXXX"}
#
# The supplier's number is stored on wallets, not profiles.
# ============================================================

class ReceivingNumberUpdate(BaseModel):
    mobile_money_number: str = Field(..., min_length=9, max_length=20)


@router.put("/wallet/seller/receiving-number")
async def update_supplier_receiving_number(
    data: ReceivingNumberUpdate,
    user=Depends(get_authenticated_user),
):
    seller_id = str(user.id)
    role, _ = require_seller(user, seller_id)

    if role != "supplier":
        raise HTTPException(
            status_code=403,
            detail="This endpoint is for supplier wallets.",
        )

    phone_number = normalize_uganda_mobile_number(
        data.mobile_money_number
    )

    wallet = ensure_wallet(seller_id, "supplier")

    update = (
        supabase.table("wallets")
        .update({
            "mobile_money_number": phone_number,
            "updated_at": utc_now(),
        })
        .eq("id", wallet["id"])
        .eq("seller_id", seller_id)
        .eq("seller_type", "supplier")
        .execute()
    )

    if not update.data:
        raise HTTPException(
            status_code=500,
            detail="Failed to save your receiving number.",
        )

    saved_wallet = update.data[0]

    return {
        "message": "Receiving number saved successfully.",
        "has_mobile_money_number": True,
        "mobile_money_number": mask_mobile_number(
            saved_wallet.get("mobile_money_number")
        ),
    }


# ============================================================
# CREDIT FARMER WALLET
# POST /api/marketplace/wallet/credit
# ============================================================

@router.post("/wallet/credit")
async def credit_wallet(
    data: WalletEarning,
    user=Depends(get_authenticated_user),
):
    role, _ = require_seller(user, data.farmer_id)

    if role != "farmer":
        raise HTTPException(
            status_code=403,
            detail="This endpoint is for farmer wallets.",
        )

    wallet = ensure_wallet(str(user.id), "farmer")
    current_balance = float(wallet.get("balance") or 0)
    new_balance = current_balance + float(data.amount)

    update = (
        supabase.table("wallets")
        .update({
            "balance": new_balance,
            "updated_at": utc_now(),
        })
        .eq("id", wallet["id"])
        .eq("seller_id", str(user.id))
        .eq("seller_type", "farmer")
        .execute()
    )

    if not update.data:
        raise HTTPException(
            status_code=500,
            detail="Failed to update farmer wallet.",
        )

    transaction = (
        supabase.table("transactions")
        .insert({
            "farmer_id": str(user.id),
            "seller_id": str(user.id),
            "seller_type": "farmer",
            "amount": float(data.amount),
            "type": "credit",
            "status": "completed",
            "reference_id": data.reference_id,
            "description": data.description,
            "created_at": utc_now(),
        })
        .execute()
    )

    if not transaction.data:
        # A balance update may already have succeeded. Reconcile
        # before retrying a credit if transaction insertion fails.
        raise HTTPException(
            status_code=500,
            detail=(
                "Wallet balance was updated, but the credit "
                "transaction could not be recorded. Reconciliation required."
            ),
        )

    return {
        "message": "Wallet credited successfully",
        "new_balance": new_balance,
        "transaction": transaction.data,
    }


# ============================================================
# WITHDRAW MONEY
# POST /api/marketplace/wallet/withdraw
# Body: {"amount": 5000}
#
# Farmer: destination from profiles.mobile_money_number.
# Supplier: destination from wallets.mobile_money_number.
# ============================================================

@router.post("/wallet/withdraw")
async def withdraw(
    data: WithdrawalCreate,
    user=Depends(get_authenticated_user),
):
    seller_id = str(user.id)
    profile = get_profile(seller_id)

    if not profile:
        raise HTTPException(status_code=404, detail="Seller profile not found.")

    seller_type = (profile.get("role") or "").strip().lower()

    if seller_type not in ALLOWED_SELLER_TYPES:
        raise HTTPException(
            status_code=403,
            detail="Only farmers and suppliers can withdraw marketplace earnings.",
        )

    try:
        amount = float(data.amount)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid withdrawal amount.")

    if amount <= 0:
        raise HTTPException(
            status_code=400,
            detail="Withdrawal amount must be greater than zero.",
        )

    # Use the supplier wallet's saved number; preserve the farmer's
    # existing profile-based destination.
    wallet = get_wallet_record(seller_id, seller_type)

    if not wallet:
        raise HTTPException(
            status_code=404,
            detail=f"{seller_type.capitalize()} wallet not found.",
        )

    raw_number = (
        wallet.get("mobile_money_number")
        if seller_type == "supplier"
        else profile.get("mobile_money_number")
    )

    if not raw_number:
        message = (
            "Save a Mobile Money receiving number in your supplier wallet "
            "before withdrawing."
            if seller_type == "supplier"
            else "Add your Mobile Money number in Payments before withdrawing."
        )
        raise HTTPException(status_code=400, detail=message)

    phone_number = normalize_uganda_mobile_number(raw_number)
    balance = float(wallet.get("balance") or 0)

    if amount > balance:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient balance. Available balance is UGX {balance:,.0f}.",
        )

    wallet_id = wallet.get("id")
    if not wallet_id:
        raise HTTPException(
            status_code=500,
            detail="Seller wallet is missing its primary key.",
        )

    transaction_id = str(uuid.uuid4())
    now = utc_now()

    withdrawal_data = {
        "farmer_id": seller_id if seller_type == "farmer" else None,
        "seller_id": seller_id,
        "seller_type": seller_type,
        "amount": amount,
        "phone_number": phone_number,
        "provider": "MTN",
        "transaction_id": transaction_id,
        "mtn_reference_id": None,
        "status": "processing",
        "created_at": now,
    }

    created = (
        supabase.table("withdrawals")
        .insert(withdrawal_data)
        .execute()
    )

    if not created.data:
        raise HTTPException(
            status_code=500,
            detail="Failed to create withdrawal record.",
        )

    # Once a payout request has been sent, a network exception does not
    # prove MTN rejected it. Keep uncertain requests processing for
    # reconciliation instead of falsely marking them failed.
    try:
        mtn_response = transfer_money(
            amount=amount,
            phone_number=phone_number,
            external_id=transaction_id,
        )
    except Exception as exc:
        print("MTN initiation outcome uncertain:", str(exc))
        raise HTTPException(
            status_code=502,
            detail=(
                "The Mobile Money request could not be confirmed. "
                "Check withdrawal status before attempting another withdrawal."
            ),
        )

    if not mtn_response.get("accepted"):
        (
            supabase.table("withdrawals")
            .update({"status": "failed"})
            .eq("transaction_id", transaction_id)
            .eq("status", "processing")
            .execute()
        )
        raise HTTPException(
            status_code=502,
            detail="Mobile Money withdrawal was not accepted by MTN.",
        )

    mtn_reference_id = mtn_response.get("reference_id")

    if not mtn_reference_id:
        print(
            "MTN accepted payout but returned no reference:",
            transaction_id,
        )
        raise HTTPException(
            status_code=502,
            detail=(
                "MTN accepted the request but did not return a reference. "
                "The withdrawal remains pending reconciliation."
            ),
        )

    reference_update = (
        supabase.table("withdrawals")
        .update({
            "mtn_reference_id": mtn_reference_id,
            "status": "processing",
        })
        .eq("transaction_id", transaction_id)
        .execute()
    )

    if not reference_update.data:
        print(
            "CRITICAL: MTN accepted payout but reference save failed:",
            transaction_id,
            mtn_reference_id,
        )
        raise HTTPException(
            status_code=500,
            detail=(
                "MTN accepted the withdrawal, but saving the reference failed. "
                "Do not retry until this transaction is reconciled."
            ),
        )

    return {
        "message": "Withdrawal request accepted and is being processed.",
        "status": "processing",
        "seller_id": seller_id,
        "seller_type": seller_type,
        "amount": amount,
        "mobile_number": phone_number,
        "provider": "MTN",
        "previous_balance": balance,
        "new_balance": balance,
        "transaction_id": transaction_id,
        "mtn_reference_id": mtn_reference_id,
        "withdrawal": reference_update.data,
    }


# ============================================================
# CONFIRM WITHDRAWAL STATUS
# GET /api/marketplace/wallet/withdraw/{transaction_id}/status
# ============================================================

@router.get("/wallet/withdraw/{transaction_id}/status")
async def confirm_withdrawal(
    transaction_id: str,
    user=Depends(get_authenticated_user),
):
    withdrawal_response = (
        supabase.table("withdrawals")
        .select("*")
        .eq("transaction_id", transaction_id)
        .limit(1)
        .execute()
    )

    if not withdrawal_response.data:
        raise HTTPException(status_code=404, detail="Withdrawal not found.")

    withdrawal = withdrawal_response.data[0]

    seller_id = withdrawal.get("seller_id") or withdrawal.get("farmer_id")
    seller_type = (
        withdrawal.get("seller_type")
        or ("farmer" if withdrawal.get("farmer_id") else "")
    ).strip().lower()

    if str(seller_id) != str(user.id):
        raise HTTPException(
            status_code=403,
            detail="You can only check your own withdrawals.",
        )

    if seller_type not in ALLOWED_SELLER_TYPES:
        raise HTTPException(
            status_code=409,
            detail="Withdrawal seller information is invalid.",
        )

    current_status = (withdrawal.get("status") or "").strip().lower()

    if current_status in {"completed", "failed"}:
        return {
            "message": f"Withdrawal already {current_status}.",
            "status": current_status,
            "transaction_id": transaction_id,
            "mtn_reference_id": withdrawal.get("mtn_reference_id"),
            "amount": withdrawal.get("amount"),
        }

    mtn_reference_id = withdrawal.get("mtn_reference_id")
    if not mtn_reference_id:
        raise HTTPException(
            status_code=409,
            detail="Withdrawal is missing its MTN reference and requires reconciliation.",
        )

    try:
        mtn_status = get_transfer_status(mtn_reference_id)
    except Exception as exc:
        print("MTN status check error:", str(exc))
        raise HTTPException(
            status_code=502,
            detail="Unable to confirm Mobile Money status. Try again later.",
        )

    transfer_status = (mtn_status.get("status") or "").strip().upper()

    if transfer_status in {"FAILED", "FAILURE"}:
        (
            supabase.table("withdrawals")
            .update({"status": "failed"})
            .eq("transaction_id", transaction_id)
            .eq("status", "processing")
            .execute()
        )
        return {
            "message": "Mobile Money withdrawal failed.",
            "status": "failed",
            "transaction_id": transaction_id,
            "mtn_reference_id": mtn_reference_id,
            "amount": withdrawal.get("amount"),
            "mtn_response": mtn_status,
        }

    if transfer_status != "SUCCESSFUL":
        return {
            "message": "Mobile Money withdrawal is still being processed.",
            "status": "processing",
            "transaction_id": transaction_id,
            "mtn_reference_id": mtn_reference_id,
            "amount": withdrawal.get("amount"),
            "mtn_status": transfer_status,
            "mtn_response": mtn_status,
        }

    # A successful debit transaction means a previous confirmation
    # already deducted the wallet. Do not deduct again.
    existing = (
        supabase.table("transactions")
        .select("*")
        .eq("reference_id", transaction_id)
        .eq("type", "debit")
        .limit(1)
        .execute()
    )

    if existing.data:
        (
            supabase.table("withdrawals")
            .update({"status": "completed"})
            .eq("transaction_id", transaction_id)
            .eq("status", "processing")
            .execute()
        )
        return {
            "message": "Withdrawal was already financially processed.",
            "status": "completed",
            "transaction_id": transaction_id,
            "mtn_reference_id": mtn_reference_id,
            "transaction": existing.data[0],
        }

    wallet = get_wallet_record(str(seller_id), seller_type)
    if not wallet:
        raise HTTPException(
            status_code=409,
            detail="Seller wallet not found. Manual reconciliation is required.",
        )

    wallet_id = wallet.get("id")
    balance = float(wallet.get("balance") or 0)
    amount = float(withdrawal.get("amount") or 0)

    if not wallet_id or amount <= 0:
        raise HTTPException(
            status_code=409,
            detail="Wallet or withdrawal data is invalid. Reconciliation required.",
        )

    if amount > balance:
        raise HTTPException(
            status_code=409,
            detail=(
                "MTN confirms the payout, but the wallet balance is insufficient "
                "for reconciliation. Manual reconciliation is required."
            ),
        )

    new_balance = balance - amount

    # Conditional update reduces the risk of a concurrent duplicate
    # deduction, but is not a substitute for a database transaction/RPC.
    wallet_update = (
        supabase.table("wallets")
        .update({
            "balance": new_balance,
            "updated_at": utc_now(),
        })
        .eq("id", wallet_id)
        .eq("seller_id", seller_id)
        .eq("seller_type", seller_type)
        .eq("balance", balance)
        .execute()
    )

    if not wallet_update.data:
        raise HTTPException(
            status_code=409,
            detail=(
                "Wallet balance changed during confirmation. "
                "Refresh and reconcile the withdrawal before retrying."
            ),
        )

    transaction_response = (
        supabase.table("transactions")
        .insert({
            "farmer_id": seller_id if seller_type == "farmer" else None,
            "seller_id": seller_id,
            "seller_type": seller_type,
            "amount": amount,
            "type": "debit",
            "status": "completed",
            "reference_id": transaction_id,
            "description": (
                "Supplier Mobile Money withdrawal"
                if seller_type == "supplier"
                else "Farmer Mobile Money withdrawal"
            ),
            "created_at": utc_now(),
        })
        .execute()
    )

    if not transaction_response.data:
        print(
            "CRITICAL: wallet deducted but debit transaction insert failed:",
            transaction_id,
        )
        raise HTTPException(
            status_code=500,
            detail=(
                "MTN payout succeeded and the wallet was updated, but the debit "
                "transaction could not be recorded. Manual reconciliation required."
            ),
        )

    completed = (
        supabase.table("withdrawals")
        .update({"status": "completed"})
        .eq("transaction_id", transaction_id)
        .eq("status", "processing")
        .execute()
    )

    return {
        "message": "Withdrawal completed successfully.",
        "status": "completed",
        "seller_id": seller_id,
        "seller_type": seller_type,
        "amount": amount,
        "mobile_number": withdrawal.get("phone_number"),
        "provider": withdrawal.get("provider"),
        "previous_balance": balance,
        "new_balance": new_balance,
        "transaction_id": transaction_id,
        "mtn_reference_id": mtn_reference_id,
        "withdrawal": completed.data,
        "transaction": transaction_response.data,
        "mtn_response": mtn_status,
    }


# ============================================================
# FARMER TRANSACTIONS
# GET /api/marketplace/transactions/{farmer_id}
# ============================================================

@router.get("/transactions/{farmer_id}")
async def transactions(
    farmer_id: str,
    user=Depends(get_authenticated_user),
):
    role, _ = require_seller(user, farmer_id)

    if role != "farmer":
        raise HTTPException(
            status_code=403,
            detail="This endpoint is for farmer transactions.",
        )

    response = (
        supabase.table("transactions")
        .select("*")
        .eq("farmer_id", farmer_id)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data


# ============================================================
# SELLER TRANSACTIONS
# GET /api/marketplace/transactions/seller/{seller_id}
# ============================================================

@router.get("/transactions/seller/{seller_id}")
async def seller_transactions(
    seller_id: str,
    seller_type: str | None = None,
    user=Depends(get_authenticated_user),
):
    role, _ = require_seller(user, seller_id, seller_type)

    query = (
        supabase.table("transactions")
        .select("*")
        .eq("seller_id", str(user.id))
        .eq("seller_type", role)
    )

    response = query.order("created_at", desc=True).execute()
    return response.data
