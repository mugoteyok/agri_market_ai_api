from fastapi import APIRouter, HTTPException

from database import supabase

from schemas.wallet import (
    WalletCreate,
    WalletEarning,
    WithdrawalCreate,
)

from services.mtn_service import transfer_money

from datetime import datetime

import uuid


router = APIRouter()


# ============================================================
# GET FARMER WALLET
#
# GET /api/marketplace/wallet/{farmer_id}
#
# Existing farmer endpoint retained.
# ============================================================

@router.get("/wallet/{farmer_id}")
async def get_wallet(
    farmer_id: str,
):

    response = (
        supabase
        .table("wallets")
        .select("*")
        .eq(
            "farmer_id",
            farmer_id,
        )
        .execute()
    )

    if response.data:
        return response.data[0]

    # --------------------------------------------------------
    # CREATE FARMER WALLET IF MISSING
    # --------------------------------------------------------

    wallet = {
        "farmer_id": farmer_id,
        "seller_id": farmer_id,
        "seller_type": "farmer",
        "balance": 0,
        "currency": "UGX",
        "updated_at": datetime.utcnow().isoformat(),
    }

    created = (
        supabase
        .table("wallets")
        .insert(wallet)
        .execute()
    )

    if not created.data:

        raise HTTPException(
            status_code=500,
            detail="Failed to create farmer wallet.",
        )

    return created.data[0]


# ============================================================
# GET SELLER WALLET
#
# Works for:
#
#   Farmer
#   Supplier
#
# GET /api/marketplace/wallet/seller/{seller_id}
# ============================================================

@router.get("/wallet/seller/{seller_id}")
async def get_seller_wallet(
    seller_id: str,
    seller_type: str | None = None,
):

    # --------------------------------------------------------
    # NORMALIZE SELLER TYPE
    # --------------------------------------------------------

    if seller_type:

        seller_type = seller_type.lower()

        if seller_type not in [
            "farmer",
            "supplier",
        ]:

            raise HTTPException(
                status_code=400,
                detail="Invalid seller type.",
            )

    # --------------------------------------------------------
    # BUILD QUERY
    # --------------------------------------------------------

    query = (
        supabase
        .table("wallets")
        .select("*")
        .eq(
            "seller_id",
            seller_id,
        )
    )

    if seller_type:

        query = query.eq(
            "seller_type",
            seller_type,
        )

    response = query.execute()

    # --------------------------------------------------------
    # WALLET FOUND
    # --------------------------------------------------------

    if response.data:
        return response.data[0]

    # --------------------------------------------------------
    # WALLET NOT FOUND
    # --------------------------------------------------------

    requested_type = (
        seller_type
        or "seller"
    )

    raise HTTPException(
        status_code=404,
        detail=(
            f"{requested_type.capitalize()} wallet not found"
        ),
    )


# ============================================================
# CREATE FARMER WALLET
#
# POST /api/marketplace/wallet/create
# ============================================================

@router.post("/wallet/create")
async def create_wallet(
    wallet: WalletCreate,
):

    existing = (
        supabase
        .table("wallets")
        .select("*")
        .eq(
            "farmer_id",
            wallet.farmer_id,
        )
        .execute()
    )

    if existing.data:

        return {
            "message": "Wallet already exists",
            "wallet": existing.data[0],
        }

    response = (
        supabase
        .table("wallets")
        .insert({
            "farmer_id": wallet.farmer_id,
            "seller_id": wallet.farmer_id,
            "seller_type": "farmer",
            "balance": 0,
            "currency": "UGX",
            "updated_at": datetime.utcnow().isoformat(),
        })
        .execute()
    )

    if not response.data:

        raise HTTPException(
            status_code=500,
            detail="Failed to create wallet.",
        )

    return {
        "message": "Wallet created successfully",
        "wallet": response.data[0],
    }


# ============================================================
# CREATE SELLER WALLET
#
# Works for:
#
#   Farmer
#   Supplier
#
# POST /api/marketplace/wallet/seller/create
# ============================================================

@router.post("/wallet/seller/create")
async def create_seller_wallet(
    seller_id: str,
    seller_type: str,
):

    seller_type = seller_type.lower()

    # --------------------------------------------------------
    # VALIDATE SELLER TYPE
    # --------------------------------------------------------

    if seller_type not in [
        "farmer",
        "supplier",
    ]:

        raise HTTPException(
            status_code=400,
            detail="Invalid seller type.",
        )

    # --------------------------------------------------------
    # CHECK EXISTING WALLET
    # --------------------------------------------------------

    existing = (
        supabase
        .table("wallets")
        .select("*")
        .eq(
            "seller_id",
            seller_id,
        )
        .eq(
            "seller_type",
            seller_type,
        )
        .execute()
    )

    if existing.data:

        return {
            "message": "Seller wallet already exists",
            "wallet": existing.data[0],
        }

    # --------------------------------------------------------
    # CREATE WALLET
    # --------------------------------------------------------

    wallet_data = {

        "farmer_id": (
            seller_id
            if seller_type == "farmer"
            else None
        ),

        "seller_id": seller_id,

        "seller_type": seller_type,

        "balance": 0,

        "currency": "UGX",

        "updated_at": datetime.utcnow().isoformat(),
    }

    response = (
        supabase
        .table("wallets")
        .insert(wallet_data)
        .execute()
    )

    if not response.data:

        raise HTTPException(
            status_code=500,
            detail="Failed to create seller wallet.",
        )

    return {
        "message": "Seller wallet created successfully",
        "wallet": response.data[0],
    }


# ============================================================
# CREDIT FARMER WALLET
#
# Existing farmer-only endpoint.
# ============================================================

@router.post("/wallet/credit")
async def credit_wallet(
    data: WalletEarning,
):

    wallet = (
        supabase
        .table("wallets")
        .select("*")
        .eq(
            "farmer_id",
            data.farmer_id,
        )
        .execute()
    )

    # --------------------------------------------------------
    # CREATE FARMER WALLET IF MISSING
    # --------------------------------------------------------

    if not wallet.data:

        wallet_insert = (
            supabase
            .table("wallets")
            .insert({
                "farmer_id": data.farmer_id,
                "seller_id": data.farmer_id,
                "seller_type": "farmer",
                "balance": 0,
                "currency": "UGX",
                "updated_at": datetime.utcnow().isoformat(),
            })
            .execute()
        )

        if not wallet_insert.data:

            raise HTTPException(
                status_code=500,
                detail="Failed to create farmer wallet.",
            )

        current_balance = 0

    else:

        current_balance = float(
            wallet.data[0].get("balance")
            or 0
        )

    # --------------------------------------------------------
    # NEW BALANCE
    # --------------------------------------------------------

    new_balance = (
        current_balance
        + float(data.amount)
    )

    # --------------------------------------------------------
    # UPDATE WALLET
    # --------------------------------------------------------

    (
        supabase
        .table("wallets")
        .update({
            "balance": new_balance,
            "updated_at": datetime.utcnow().isoformat(),
        })
        .eq(
            "farmer_id",
            data.farmer_id,
        )
        .execute()
    )

    # --------------------------------------------------------
    # SAVE CREDIT TRANSACTION
    # --------------------------------------------------------

    transaction = (
        supabase
        .table("transactions")
        .insert({
            "farmer_id": data.farmer_id,
            "seller_id": data.farmer_id,
            "seller_type": "farmer",
            "amount": data.amount,
            "type": "credit",
            "status": "completed",
            "reference_id": data.reference_id,
            "description": data.description,
            "created_at": datetime.utcnow().isoformat(),
        })
        .execute()
    )

    return {
        "message": "Wallet credited successfully",
        "new_balance": new_balance,
        "transaction": transaction.data,
    }


# ============================================================
# WITHDRAW MONEY
#
# POST /api/marketplace/wallet/withdraw
#
# Supports:
#
#   farmer
#   supplier
# ============================================================

@router.post("/wallet/withdraw")
async def withdraw(
    data: WithdrawalCreate,
):

    # ========================================================
    # IDENTIFY SELLER
    # ========================================================

    seller_id = (
        data.seller_id
        or data.farmer_id
    )

    seller_type = (
        data.seller_type
        or "farmer"
    ).strip().lower()

    # ========================================================
    # VALIDATE SELLER ID
    # ========================================================

    if not seller_id:

        raise HTTPException(
            status_code=400,
            detail="Seller ID is required.",
        )

    seller_id = seller_id.strip()

    # ========================================================
    # VALIDATE SELLER TYPE
    # ========================================================

    if seller_type not in [
        "farmer",
        "supplier",
    ]:

        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid seller type. "
                "Must be farmer or supplier."
            ),
        )

    # ========================================================
    # VALIDATE AMOUNT
    # ========================================================

    try:

        amount = float(data.amount)

    except (TypeError, ValueError):

        raise HTTPException(
            status_code=400,
            detail="Invalid withdrawal amount.",
        )

    if amount <= 0:

        raise HTTPException(
            status_code=400,
            detail=(
                "Withdrawal amount must be "
                "greater than zero."
            ),
        )

    # ========================================================
    # NORMALIZE PHONE NUMBER
    # ========================================================

    phone_number = (
        data.mobile_number
        .strip()
        .replace(" ", "")
        .replace("-", "")
        .replace("+", "")
    )

    if phone_number.startswith("0"):

        phone_number = (
            "256"
            + phone_number[1:]
        )

    # ========================================================
    # VALIDATE UGANDA PHONE NUMBER
    # ========================================================

    if not phone_number.isdigit():

        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid Mobile Money phone number."
            ),
        )

    if not phone_number.startswith("256"):

        raise HTTPException(
            status_code=400,
            detail=(
                "Use a valid Uganda Mobile Money number."
            ),
        )

    if len(phone_number) != 12:

        raise HTTPException(
            status_code=400,
            detail=(
                "Use a valid Uganda Mobile Money number."
            ),
        )

    # ========================================================
    # FIND EXACT SELLER WALLET
    # ========================================================

    wallet_response = (
        supabase
        .table("wallets")
        .select("*")
        .eq(
            "seller_id",
            seller_id,
        )
        .eq(
            "seller_type",
            seller_type,
        )
        .limit(1)
        .execute()
    )

    # ========================================================
    # WALLET NOT FOUND
    # ========================================================

    if not wallet_response.data:

        raise HTTPException(
            status_code=404,
            detail=(
                f"{seller_type.capitalize()} "
                "wallet not found."
            ),
        )

    wallet = wallet_response.data[0]

    # ========================================================
    # CONFIRM WALLET IDENTITY
    # ========================================================

    actual_seller_id = wallet.get(
        "seller_id"
    )

    actual_seller_type = (
        wallet.get("seller_type")
        or ""
    ).strip().lower()

    if str(actual_seller_id) != str(seller_id):

        raise HTTPException(
            status_code=500,
            detail=(
                "Wallet seller ID does not match "
                "withdrawal seller."
            ),
        )

    if actual_seller_type != seller_type:

        raise HTTPException(
            status_code=500,
            detail=(
                "Wallet seller type does not match "
                "withdrawal seller."
            ),
        )

    # ========================================================
    # CONFIRM WALLET PRIMARY KEY
    # ========================================================

    wallet_id = wallet.get("id")

    if not wallet_id:

        raise HTTPException(
            status_code=500,
            detail=(
                "Seller wallet is missing its "
                "primary key."
            ),
        )

    # ========================================================
    # READ BALANCE
    # ========================================================

    balance = float(
        wallet.get("balance")
        or 0
    )

    # ========================================================
    # CHECK BALANCE
    # ========================================================

    if amount > balance:

        raise HTTPException(
            status_code=400,
            detail=(
                f"Insufficient balance. "
                f"Available balance is "
                f"UGX {balance:,.0f}."
            ),
        )

    # ========================================================
    # CREATE WITHDRAWAL ID
    # ========================================================

    transaction_id = str(
        uuid.uuid4()
    )

    now = datetime.utcnow().isoformat()

    # ========================================================
    # CREATE WITHDRAWAL RECORD
    # ========================================================

    withdrawal_data = {

        "farmer_id": (
            seller_id
            if seller_type == "farmer"
            else None
        ),

        "amount":
            amount,

        "phone_number":
            phone_number,

        "provider":
            data.network.value,

        "transaction_id":
            transaction_id,

        "status":
            "processing",

        "created_at":
            now,
    }

    withdrawal_response = (
        supabase
        .table("withdrawals")
        .insert(
            withdrawal_data
        )
        .execute()
    )

    if not withdrawal_response.data:

        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to create withdrawal record."
            ),
        )

    # ========================================================
    # SEND MOBILE MONEY
    # ========================================================

    try:

        mtn_response = transfer_money(

            amount=amount,

            phone_number=phone_number,

            external_id=transaction_id,

        )

        # ====================================================
        # CHECK MTN RESPONSE
        #
        # transfer_money() returns a dictionary:
        #
        # {
        #     "accepted": bool,
        #     "status_code": int,
        #     "reference_id": str,
        #     "external_id": str,
        #     "response_text": str,
        # }
        # ====================================================

        if not mtn_response.get("accepted"):

            status_code = mtn_response.get(
                "status_code"
            )

            response_text = mtn_response.get(
                "response_text"
            )

            raise Exception(
                f"MTN transfer failed. "
                f"Status: {status_code}. "
                f"Response: {response_text}"
            )

        # ====================================================
        # SAVE MTN TRANSFER REFERENCE
        # ====================================================

        mtn_reference_id = mtn_response.get(
            "reference_id"
        )

        # ====================================================
        # LOG SUCCESS
        # ====================================================

        print(
            "================================================"
        )

        print(
            "MOBILE MONEY WITHDRAWAL ACCEPTED"
        )

        print(
            "seller_id:",
            seller_id,
        )

        print(
            "seller_type:",
            seller_type,
        )

        print(
            "amount:",
            amount,
        )

        print(
            "phone:",
            phone_number,
        )

        print(
            "transaction_id:",
            transaction_id,
        )

        print(
            "mtn_reference_id:",
            mtn_reference_id,
        )

        print(
            "================================================"
        )

        # ====================================================
        # CALCULATE NEW BALANCE
        # ====================================================

        new_balance = (
            balance
            - amount
        )

        # ====================================================
        # DEDUCT FROM EXACT WALLET
        # ====================================================

        wallet_update_response = (
            supabase
            .table("wallets")
            .update({

                "balance":
                    new_balance,

                "updated_at":
                    datetime.utcnow().isoformat(),

            })
            .eq(
                "id",
                wallet_id,
            )
            .eq(
                "seller_id",
                seller_id,
            )
            .eq(
                "seller_type",
                seller_type,
            )
            .execute()
        )

        # ====================================================
        # VERIFY WALLET WAS ACTUALLY UPDATED
        # ====================================================

        if not wallet_update_response.data:

            print(
                "CRITICAL: MTN payout accepted but "
                "wallet deduction failed."
            )

            print(
                "seller_id:",
                seller_id,
            )

            print(
                "seller_type:",
                seller_type,
            )

            print(
                "transaction_id:",
                transaction_id,
            )

            print(
                "mtn_reference_id:",
                mtn_reference_id,
            )

            raise HTTPException(
                status_code=500,
                detail=(
                    "Mobile Money payment was accepted, "
                    "but the seller wallet could not be "
                    "updated. The withdrawal requires "
                    "reconciliation."
                ),
            )

        # ====================================================
        # CREATE SELLER WITHDRAWAL TRANSACTION
        # ====================================================

        transaction_response = (
            supabase
            .table("transactions")
            .insert({

                "farmer_id": (
                    seller_id
                    if seller_type == "farmer"
                    else None
                ),

                "seller_id":
                    seller_id,

                "seller_type":
                    seller_type,

                "amount":
                    amount,

                "type":
                    "debit",

                "status":
                    "completed",

                "reference_id":
                    transaction_id,

                "description": (
                    "Supplier Mobile Money withdrawal"
                    if seller_type == "supplier"
                    else
                    "Farmer Mobile Money withdrawal"
                ),

                "created_at":
                    now,

            })
            .execute()
        )

        # ====================================================
        # VERIFY TRANSACTION
        # ====================================================

        if not transaction_response.data:

            print(
                "CRITICAL: Wallet deducted but "
                "withdrawal transaction was not created."
            )

            print(
                "seller_id:",
                seller_id,
            )

            print(
                "seller_type:",
                seller_type,
            )

            print(
                "amount:",
                amount,
            )

            print(
                "transaction_id:",
                transaction_id,
            )

            print(
                "mtn_reference_id:",
                mtn_reference_id,
            )

        # ====================================================
        # MARK WITHDRAWAL COMPLETED
        # ====================================================

        completed_withdrawal = (
            supabase
            .table("withdrawals")
            .update({

                "status":
                    "completed",

            })
            .eq(
                "transaction_id",
                transaction_id,
            )
            .execute()
        )

        # ====================================================
        # RETURN SUCCESS
        # ====================================================

        return {

            "message":
                "Withdrawal completed successfully.",

            "seller_id":
                seller_id,

            "seller_type":
                seller_type,

            "amount":
                amount,

            "mobile_number":
                phone_number,

            "provider":
                data.network.value,

            "previous_balance":
                balance,

            "new_balance":
                new_balance,

            "mtn_reference_id":
                mtn_reference_id,

            "withdrawal":
                completed_withdrawal.data,

            "transaction":
                transaction_response.data,

        }

    # ========================================================
    # HTTP EXCEPTION
    # ========================================================

    except HTTPException as e:

        print(
            "WITHDRAWAL HTTP ERROR:",
            str(e),
        )

        raise

    # ========================================================
    # MOBILE MONEY / OTHER FAILURE
    # ========================================================

    except Exception as e:

        print(
            "MOBILE MONEY WITHDRAWAL ERROR:",
            str(e),
        )

        (
            supabase
            .table("withdrawals")
            .update({
                "status": "failed",
            })
            .eq(
                "transaction_id",
                transaction_id,
            )
            .execute()
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "Mobile Money withdrawal failed. "
                "Your wallet balance was not deducted."
            ),
        )


# ============================================================
# FARMER TRANSACTIONS
#
# GET /api/marketplace/transactions/{farmer_id}
# ============================================================

@router.get("/transactions/{farmer_id}")
async def transactions(
    farmer_id: str,
):

    response = (
        supabase
        .table("transactions")
        .select("*")
        .eq(
            "farmer_id",
            farmer_id,
        )
        .order(
            "created_at",
            desc=True,
        )
        .execute()
    )

    return response.data


# ============================================================
# SELLER TRANSACTIONS
#
# Works for:
#
#   Farmer
#   Supplier
#
# GET /api/marketplace/transactions/seller/{seller_id}
# ============================================================

@router.get("/transactions/seller/{seller_id}")
async def seller_transactions(
    seller_id: str,
    seller_type: str | None = None,
):

    # --------------------------------------------------------
    # NORMALIZE SELLER TYPE
    # --------------------------------------------------------

    if seller_type:

        seller_type = seller_type.lower()

        if seller_type not in [
            "farmer",
            "supplier",
        ]:

            raise HTTPException(
                status_code=400,
                detail="Invalid seller type.",
            )

    # --------------------------------------------------------
    # BUILD QUERY
    # --------------------------------------------------------

    query = (
        supabase
        .table("transactions")
        .select("*")
        .eq(
            "seller_id",
            seller_id,
        )
    )

    if seller_type:

        query = query.eq(
            "seller_type",
            seller_type,
        )

    response = (
        query
        .order(
            "created_at",
            desc=True,
        )
        .execute()
    )

    return response.data
