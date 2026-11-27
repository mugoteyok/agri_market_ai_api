
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from database import get_admin_supabase
from auth import get_authenticated_user
from schemas.wallet import (
    WalletCreate,
    WithdrawalCreate,
)
from services.mtn_service import (
    transfer_money,
    get_transfer_status,
    validate_disbursement_config,
    MTNTransferOutcomeUnknown,
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
        get_admin_supabase().table("profiles")
        .select("id, role, mobile_money_number")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    return response.data


def get_wallet_record(seller_id: str, seller_type: str):
    response = (
        get_admin_supabase().table("wallets")
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

    response = get_admin_supabase().table("wallets").insert(wallet_data).execute()

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
        get_admin_supabase().table("wallets")
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
# DISABLED WALLET CREDIT
# POST /api/marketplace/wallet/credit
# Credits must originate from verified marketplace settlement.
# ============================================================

@router.post("/wallet/credit", include_in_schema=False)
async def credit_wallet_disabled(_user=Depends(get_authenticated_user)):
    raise HTTPException(status_code=410, detail="Manual wallet credits are disabled. Credits must come from verified marketplace settlement.")


# ============================================================
# WITHDRAW MONEY
# POST /api/marketplace/wallet/withdraw
#
# Funds are reserved atomically before MTN submission.
# The MTN reference is persisted before the transfer is sent.
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
        amount = Decimal(str(data.amount))
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid withdrawal amount.")

    if not amount.is_finite() or amount <= 0:
        raise HTTPException(
            status_code=400,
            detail="Withdrawal amount must be a finite value greater than zero.",
        )

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

    # Validate credentials before reserving funds.
    try:
        validate_disbursement_config()
    except Exception as exc:
        print("MTN disbursement configuration is unavailable:", str(exc))
        raise HTTPException(
            status_code=503,
            detail="MTN disbursement is not configured. No funds were reserved.",
        )

    previous_balance = Decimal(str(wallet.get("balance") or 0))
    transaction_id = str(uuid.uuid4())
    mtn_reference_id = str(uuid.uuid4())

    try:
        result = (
            get_admin_supabase()
            .rpc(
                "reserve_wallet_withdrawal",
                {
                    "p_seller_id": seller_id,
                    "p_seller_type": seller_type,
                    "p_amount": str(amount),
                    "p_phone_number": phone_number,
                    "p_transaction_id": transaction_id,
                    "p_mtn_reference_id": mtn_reference_id,
                },
            )
            .execute()
            .data
        )
    except Exception as exc:
        error_text = str(exc).lower()
        if "insufficient wallet balance" in error_text:
            raise HTTPException(status_code=400, detail="Insufficient wallet balance.")
        if "duplicate key" in error_text or "unique constraint" in error_text:
            raise HTTPException(
                status_code=409,
                detail="A withdrawal is already being processed. Check its status.",
            )
        print("Withdrawal reservation failed:", str(exc))
        raise HTTPException(status_code=500, detail="Could not reserve withdrawal funds.")

    if not isinstance(result, dict):
        raise HTTPException(status_code=502, detail="Unexpected reservation response.")

    reservation_state = result.get("result")
    withdrawal_record = result.get("withdrawal") or {}

    # Replays never submit another transfer to MTN.
    if reservation_state in {"duplicate_request", "already_processing"}:
        current_wallet = get_wallet_record(seller_id, seller_type) or wallet
        current_balance = float(current_wallet.get("balance") or 0)
        return {
            "message": "An earlier withdrawal is already being processed. Check its status before retrying.",
            "status": withdrawal_record.get("status", "processing"),
            "transaction_id": withdrawal_record.get("transaction_id"),
            "mtn_reference_id": withdrawal_record.get("mtn_reference_id"),
            "amount": float(withdrawal_record.get("amount") or amount),
            "seller_id": seller_id,
            "seller_type": seller_type,
            "previous_balance": current_balance,
            "new_balance": current_balance,
        }

    if reservation_state != "reserved":
        raise HTTPException(status_code=409, detail="Withdrawal funds could not be reserved.")

    try:
        mtn_response = transfer_money(
            amount=float(amount),
            phone_number=phone_number,
            external_id=transaction_id,
            reference_id=mtn_reference_id,
        )
    except MTNTransferOutcomeUnknown as exc:
        # MTN may have received the request. Keep funds reserved.
        print("MTN transfer outcome unknown:", transaction_id, str(exc))
        current_wallet = get_wallet_record(seller_id, seller_type) or {}
        return {
            "message": "MTN confirmation is pending. Funds remain reserved; check withdrawal status before retrying.",
            "status": "processing",
            "transaction_id": transaction_id,
            "mtn_reference_id": mtn_reference_id,
            "amount": float(amount),
            "seller_id": seller_id,
            "seller_type": seller_type,
            "previous_balance": float(previous_balance),
            "new_balance": float(current_wallet.get("balance") or 0),
            "reconciliation_required": True,
        }
    except Exception as exc:
        # Token/configuration failures occur before the transfer POST.
        try:
            release = (
                get_admin_supabase()
                .rpc(
                    "release_wallet_withdrawal",
                    {
                        "p_transaction_id": transaction_id,
                        "p_failure_reason": "MTN payout could not be submitted",
                    },
                )
                .execute()
                .data
            )
            if not isinstance(release, dict) or release.get("result") not in {
                "released", "already_released"
            }:
                raise RuntimeError("Unexpected release response")
        except Exception as release_exc:
            print("CRITICAL: failed to release withdrawal:", transaction_id, str(release_exc))
            raise HTTPException(
                status_code=500,
                detail=f"Withdrawal requires reconciliation. Reference: {transaction_id}",
            )
        print("MTN transfer could not be submitted:", str(exc))
        raise HTTPException(
            status_code=502,
            detail="MTN payout could not be submitted. Reserved funds were restored.",
        )

    if not mtn_response.get("accepted"):
        status_code = mtn_response.get("status_code")

        # A server/timeout/rate-limit response may be ambiguous.
        # Do not refund until the provider confirms the transfer failed.
        if (
            status_code is None
            or not 400 <= status_code < 500
            or status_code in {408, 409, 425, 429}
        ):
            current_wallet = get_wallet_record(seller_id, seller_type) or {}
            return {
                "message": "MTN returned an uncertain response. Funds remain reserved while the transfer is reconciled.",
                "status": "processing",
                "transaction_id": transaction_id,
                "mtn_reference_id": mtn_reference_id,
                "amount": float(amount),
                "seller_id": seller_id,
                "seller_type": seller_type,
                "previous_balance": float(previous_balance),
                "new_balance": float(current_wallet.get("balance") or 0),
                "reconciliation_required": True,
            }

        try:
            release = (
                get_admin_supabase()
                .rpc(
                    "release_wallet_withdrawal",
                    {
                        "p_transaction_id": transaction_id,
                        "p_failure_reason": f"MTN rejected transfer (HTTP {status_code})",
                    },
                )
                .execute()
                .data
            )
            if not isinstance(release, dict) or release.get("result") not in {
                "released", "already_released"
            }:
                raise RuntimeError("Unexpected release response")
        except Exception as exc:
            print("CRITICAL: MTN rejection release failed:", transaction_id, str(exc))
            raise HTTPException(
                status_code=500,
                detail=f"Withdrawal requires reconciliation. Reference: {transaction_id}",
            )
        raise HTTPException(
            status_code=502,
            detail="MTN rejected the withdrawal. Reserved funds were restored.",
        )

    current_wallet = get_wallet_record(seller_id, seller_type) or {}
    return {
        "message": "Withdrawal request accepted and is being processed.",
        "status": "processing",
        "seller_id": seller_id,
        "seller_type": seller_type,
        "amount": float(amount),
        "mobile_number": phone_number,
        "provider": "MTN",
        "previous_balance": float(previous_balance),
        "new_balance": float(current_wallet.get("balance") or 0),
        "transaction_id": transaction_id,
        "mtn_reference_id": mtn_reference_id,
        "withdrawal": withdrawal_record,
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
    response = (
        get_admin_supabase()
        .table("withdrawals")
        .select("*")
        .eq("transaction_id", transaction_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail="Withdrawal not found.")

    withdrawal = response.data[0]
    seller_id = withdrawal.get("seller_id") or withdrawal.get("farmer_id")
    seller_type = (
        withdrawal.get("seller_type")
        or ("farmer" if withdrawal.get("farmer_id") else "")
    ).strip().lower()

    if str(seller_id) != str(user.id):
        raise HTTPException(status_code=403, detail="You can only check your own withdrawals.")

    if seller_type not in ALLOWED_SELLER_TYPES:
        raise HTTPException(status_code=409, detail="Withdrawal seller information is invalid.")

    current_status = (withdrawal.get("status") or "").strip().lower()
    if current_status in {"completed", "failed"}:
        return {
            "message": f"Withdrawal already {current_status}.",
            "status": current_status,
            "transaction_id": transaction_id,
            "mtn_reference_id": withdrawal.get("mtn_reference_id"),
            "amount": withdrawal.get("amount"),
            "funds_reserved": withdrawal.get("funds_reserved", False),
        }

    if withdrawal.get("funds_reserved") is not True:
        raise HTTPException(
            status_code=409,
            detail="This legacy withdrawal has no active funds reservation and cannot use the new workflow.",
        )

    reference_id = withdrawal.get("mtn_reference_id")
    if not reference_id:
        raise HTTPException(status_code=409, detail="Withdrawal MTN reference is missing.")

    try:
        mtn_status = get_transfer_status(reference_id)
    except Exception as exc:
        print("MTN status check error:", str(exc))
        raise HTTPException(
            status_code=502,
            detail="Unable to confirm Mobile Money status. Funds remain reserved.",
        )

    status = (mtn_status.get("status") or "").strip().upper()

    if status in {"SUCCESSFUL", "SUCCESS"}:
        result = (
            get_admin_supabase()
            .rpc(
                "complete_wallet_withdrawal",
                {
                    "p_transaction_id": transaction_id,
                    "p_financial_transaction_id": mtn_status.get("financialTransactionId"),
                },
            )
            .execute()
            .data
        )
        if not isinstance(result, dict) or result.get("result") not in {
            "completed", "already_completed"
        }:
            raise HTTPException(status_code=409, detail="Withdrawal completion requires reconciliation.")

        current_wallet = get_wallet_record(seller_id, seller_type) or {}
        return {
            "message": "Withdrawal completed successfully.",
            "status": "completed",
            "seller_id": seller_id,
            "seller_type": seller_type,
            "amount": withdrawal.get("amount"),
            "transaction_id": transaction_id,
            "mtn_reference_id": reference_id,
            "financial_transaction_id": mtn_status.get("financialTransactionId"),
            "new_balance": float(current_wallet.get("balance") or 0),
            "withdrawal": result.get("withdrawal"),
            "mtn_response": mtn_status,
        }

    if status in {"FAILED", "FAILURE"}:
        reason = (
            mtn_status.get("reason")
            or mtn_status.get("message")
            or "MTN confirmed transfer failure"
        )
        result = (
            get_admin_supabase()
            .rpc(
                "release_wallet_withdrawal",
                {
                    "p_transaction_id": transaction_id,
                    "p_failure_reason": str(reason)[:500],
                },
            )
            .execute()
            .data
        )
        if not isinstance(result, dict) or result.get("result") not in {
            "released", "already_released"
        }:
            raise HTTPException(status_code=409, detail="Withdrawal release requires reconciliation.")

        current_wallet = get_wallet_record(seller_id, seller_type) or {}
        return {
            "message": "Withdrawal failed. Reserved funds were restored.",
            "status": "failed",
            "seller_id": seller_id,
            "seller_type": seller_type,
            "amount": withdrawal.get("amount"),
            "transaction_id": transaction_id,
            "mtn_reference_id": reference_id,
            "new_balance": float(current_wallet.get("balance") or 0),
            "withdrawal": result.get("withdrawal"),
            "mtn_response": mtn_status,
        }

    return {
        "message": "Mobile Money withdrawal is still being processed.",
        "status": "processing",
        "transaction_id": transaction_id,
        "mtn_reference_id": reference_id,
        "amount": withdrawal.get("amount"),
        "mtn_status": status,
        "funds_reserved": True,
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
        get_admin_supabase().table("transactions")
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
        get_admin_supabase().table("transactions")
        .select("*")
        .eq("seller_id", str(user.id))
        .eq("seller_type", role)
    )

    response = query.order("created_at", desc=True).execute()
    return response.data
