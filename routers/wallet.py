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
    #
    # This is retained for backward compatibility with the
    # existing farmer wallet implementation.
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
# Farmer
# Supplier
#
# GET /api/marketplace/wallet/seller/{seller_id}
#
# IMPORTANT:
#
# GET ONLY READS.
#
# If wallet does not exist, return 404.
# Creation is handled by:
#
# POST /wallet/seller/create
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
    #
    # DO NOT CREATE HERE.
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
# Farmer
# Supplier
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
#
# Marketplace order completion should use the complete-order
# settlement logic instead of calling this separately.
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
# Works with:
#
#   farmer
#   supplier
#
# IMPORTANT:
#
# The wallet is identified using:
#
#     seller_id
#     seller_type
#
# This prevents a supplier from accidentally using a farmer
# wallet belonging to the same UUID.
#
# SUPPLIER WITHDRAWAL:
#
#     seller_id   = supplier UUID
#     seller_type = supplier
#
#     farmer_id   = NULL
#
# FARMER WITHDRAWAL:
#
#     seller_id   = farmer UUID
#     seller_type = farmer
#
#     farmer_id   = farmer UUID
# ============================================================

@router.post("/wallet/withdraw")
async def withdraw(
    data: WithdrawalCreate,
):

    # ========================================================
    # IDENTIFY SELLER
    # ========================================================

    seller_id = data.farmer_id

    seller_type = (
        data.seller_type
        or "farmer"
    ).strip().lower()

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
    # VALIDATE SELLER ID
    # ========================================================

    if not seller_id:

        raise HTTPException(
            status_code=400,
            detail="Seller ID is required.",
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
    #
    # Examples:
    #
    # 0772123456
    #     ->
    # 256772123456
    #
    # +256772123456
    #     ->
    # 256772123456
    #
    # 256772123456
    #     ->
    # 256772123456
    # ========================================================

    phone_number = (
        data.mobile_number
        .strip()
        .replace(" ", "")
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
            detail="Invalid Mobile Money phone number.",
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
    #
    # IMPORTANT:
    #
    # NEVER search by farmer_id here.
    #
    # Supplier:
    #
    # seller_id   = supplier UUID
    # seller_type = supplier
    #
    # Farmer:
    #
    # seller_id   = farmer UUID
    # seller_type = farmer
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

    if not wallet_response.data:

        raise HTTPException(
            status_code=404,
            detail=(
                f"{seller_type.capitalize()} wallet not found."
            ),
        )

    wallet = wallet_response.data[0]

    # ========================================================
    # CONFIRM WALLET IDENTITY
    #
    # Extra safety check.
    # ========================================================

    actual_seller_id = wallet.get(
        "seller_id"
    )

    actual_seller_type = (
        wallet.get("seller_type")
        or ""
    ).lower()

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
    #
    # IMPORTANT:
    #
    # Supplier:
    #
    #     farmer_id = NULL
    #
    # Farmer:
    #
    #     farmer_id = seller_id
    #
    # This prevents supplier withdrawals from being recorded
    # as farmer withdrawals.
    # ========================================================

    withdrawal_data = {

        "farmer_id": (
            seller_id
            if seller_type == "farmer"
            else None
        ),

        "amount": amount,

        "phone_number": phone_number,

        "provider": data.network.value,

        "transaction_id": transaction_id,

        "status": "processing",

        "created_at": now,
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
    #
    # The number sent to MTN is the number supplied for this
    # specific withdrawal.
    #
    # It is NOT derived from farmer_id.
    # ========================================================

    try:

        mtn_response = transfer_money(

            amount=amount,

            phone_number=phone_number,

            external_id=transaction_id,

        )

        # ====================================================
        # CHECK MTN RESPONSE
        # ====================================================

        if mtn_response.status_code not in [
            200,
            202,
        ]:

            raise Exception(
                mtn_response.text
            )

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
            "================================================"
        )

        # ====================================================
        # DEDUCT FROM EXACT WALLET
        #
        # IMPORTANT:
        #
        # Use the wallet primary key AND seller identity.
        #
        # This guarantees that a supplier withdrawal modifies
        # the supplier wallet, not a farmer wallet.
        # ====================================================

        new_balance = (
            balance
            - amount
        )

        wallet_update = (
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
                wallet["id"],
            )
            .eq(
                "seller_id",
                seller_id,
            )
            .eq(
                "seller_type",
                seller_type,
            )
        )

        wallet_update_response = (
            wallet_update.execute()
        )

        if not wallet_update_response.data:

            raise HTTPException(
                status_code=500,
                detail=(
                    "Mobile Money payment was accepted "
                    "but wallet balance could not be "
                    "updated."
                ),
            )

        # ====================================================
        # CREATE WITHDRAWAL TRANSACTION
        #
        # SUPPLIER:
        #
        # farmer_id = NULL
        # seller_id = supplier UUID
        # seller_type = supplier
        #
        # FARMER:
        #
        # farmer_id = farmer UUID
        # seller_id = farmer UUID
        # seller_type = farmer
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

                "description":
                    (
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

        if not transaction_response.data:

            print(
                "WARNING: Wallet deducted but "
                "withdrawal transaction was not created."
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

            "withdrawal":
                completed_withdrawal.data,

            "transaction":
                transaction_response.data,

        }

    # ========================================================
    # MOBILE MONEY FAILED
    # ========================================================

    except HTTPException:

        # ----------------------------------------------------
        # Preserve HTTPException without converting it into
        # a generic 500.
        # ----------------------------------------------------

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

        raise

    except Exception as e:

        print(
            "MOBILE MONEY WITHDRAWAL ERROR:",
            str(e),
        )

        # ----------------------------------------------------
        # Mark withdrawal failed.
        #
        # IMPORTANT:
        #
        # The wallet has NOT been deducted yet because the
        # deduction happens only after transfer_money succeeds.
        # ----------------------------------------------------

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
# Farmer
# Supplier
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
