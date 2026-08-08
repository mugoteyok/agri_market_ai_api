
from fastapi import APIRouter, HTTPException

from database import supabase

from schemas.wallet import (
    WalletCreate,
    WalletEarning,
    WithdrawalCreate
)

from services.mtn_service import transfer_money

from datetime import datetime

import uuid


router = APIRouter()


# ============================================================
# GET FARMER WALLET
#
# Existing endpoint kept for backward compatibility.
#
# GET /api/marketplace/wallet/{farmer_id}
# ============================================================

@router.get("/wallet/{farmer_id}")
async def get_wallet(
    farmer_id: str
):

    response = (
        supabase
        .table("wallets")
        .select("*")
        .eq(
            "farmer_id",
            farmer_id
        )
        .execute()
    )

    if response.data:

        return response.data[0]


    # --------------------------------------------------------
    # CREATE FARMER WALLET IF MISSING
    # --------------------------------------------------------

    wallet = {

        "farmer_id":
            farmer_id,

        "seller_id":
            farmer_id,

        "seller_type":
            "farmer",

        "balance":
            0,

        "currency":
            "UGX",

        "updated_at":
            datetime.utcnow().isoformat()
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
            detail="Failed to create farmer wallet."
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
# Optional:
#
# ?seller_type=farmer
# ?seller_type=supplier
# ============================================================

@router.get("/wallet/seller/{seller_id}")
async def get_seller_wallet(
    seller_id: str,
    seller_type: str | None = None
):

    query = (
        supabase
        .table("wallets")
        .select("*")
        .eq(
            "seller_id",
            seller_id
        )
    )


    if seller_type:

        seller_type = seller_type.lower()

        if seller_type not in [
            "farmer",
            "supplier"
        ]:

            raise HTTPException(
                status_code=400,
                detail="Invalid seller type."
            )


        query = query.eq(
            "seller_type",
            seller_type
        )


    response = query.execute()


    if response.data:

        return response.data[0]


    # --------------------------------------------------------
    # DETERMINE SELLER TYPE
    # --------------------------------------------------------

    wallet_seller_type = (
        seller_type
        or "farmer"
    )


    # --------------------------------------------------------
    # CREATE SELLER WALLET
    # --------------------------------------------------------

    wallet_data = {

        "farmer_id":
            seller_id
            if wallet_seller_type == "farmer"
            else None,

        "seller_id":
            seller_id,

        "seller_type":
            wallet_seller_type,

        "balance":
            0,

        "currency":
            "UGX",

        "updated_at":
            datetime.utcnow().isoformat()
    }


    created = (
        supabase
        .table("wallets")
        .insert(wallet_data)
        .execute()
    )


    if not created.data:

        raise HTTPException(
            status_code=500,
            detail="Failed to create seller wallet."
        )


    return created.data[0]


# ============================================================
# CREATE FARMER WALLET
#
# POST /api/marketplace/wallet/create
# ============================================================

@router.post("/wallet/create")
async def create_wallet(
    wallet: WalletCreate
):

    existing = (
        supabase
        .table("wallets")
        .select("*")
        .eq(
            "farmer_id",
            wallet.farmer_id
        )
        .execute()
    )


    if existing.data:

        return {

            "message":
                "Wallet already exists",

            "wallet":
                existing.data[0]
        }


    response = (
        supabase
        .table("wallets")
        .insert({

            "farmer_id":
                wallet.farmer_id,

            "seller_id":
                wallet.farmer_id,

            "seller_type":
                "farmer",

            "balance":
                0,

            "currency":
                "UGX",

            "updated_at":
                datetime.utcnow().isoformat()
        })
        .execute()
    )


    if not response.data:

        raise HTTPException(
            status_code=500,
            detail="Failed to create wallet."
        )


    return response.data[0]


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
    seller_type: str
):

    seller_type = seller_type.lower()


    if seller_type not in [
        "farmer",
        "supplier"
    ]:

        raise HTTPException(
            status_code=400,
            detail="Invalid seller type."
        )


    existing = (
        supabase
        .table("wallets")
        .select("*")
        .eq(
            "seller_id",
            seller_id
        )
        .eq(
            "seller_type",
            seller_type
        )
        .execute()
    )


    if existing.data:

        return {

            "message":
                "Seller wallet already exists",

            "wallet":
                existing.data[0]
        }


    wallet_data = {

        "farmer_id":
            seller_id
            if seller_type == "farmer"
            else None,

        "seller_id":
            seller_id,

        "seller_type":
            seller_type,

        "balance":
            0,

        "currency":
            "UGX",

        "updated_at":
            datetime.utcnow().isoformat()
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
            detail="Failed to create seller wallet."
        )


    return {

        "message":
            "Seller wallet created successfully",

        "wallet":
            response.data[0]
    }


# ============================================================
# CREDIT FARMER WALLET
#
# POST /api/marketplace/wallet/credit
#
# Marketplace order completion should use the complete-order
# endpoint rather than calling this endpoint separately.
#
# This prevents double wallet credits.
# ============================================================

@router.post("/wallet/credit")
async def credit_wallet(
    data: WalletEarning
):

    wallet = (
        supabase
        .table("wallets")
        .select("*")
        .eq(
            "farmer_id",
            data.farmer_id
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

                "farmer_id":
                    data.farmer_id,

                "seller_id":
                    data.farmer_id,

                "seller_type":
                    "farmer",

                "balance":
                    0,

                "currency":
                    "UGX",

                "updated_at":
                    datetime.utcnow().isoformat()
            })
            .execute()
        )


        if not wallet_insert.data:

            raise HTTPException(
                status_code=500,
                detail="Failed to create farmer wallet."
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
        current_balance +
        float(data.amount)
    )


    # --------------------------------------------------------
    # UPDATE WALLET
    # --------------------------------------------------------

    supabase \
        .table("wallets") \
        .update({

            "balance":
                new_balance,

            "updated_at":
                datetime.utcnow().isoformat()

        }) \
        .eq(
            "farmer_id",
            data.farmer_id
        ) \
        .execute()


    # --------------------------------------------------------
    # SAVE CREDIT TRANSACTION
    # --------------------------------------------------------

    transaction = (
        supabase
        .table("transactions")
        .insert({

            "farmer_id":
                data.farmer_id,

            "seller_id":
                data.farmer_id,

            "seller_type":
                "farmer",

            "amount":
                data.amount,

            "type":
                "credit",

            "status":
                "completed",

            "reference_id":
                data.reference_id,

            "description":
                data.description,

            "created_at":
                datetime.utcnow().isoformat()
        })
        .execute()
    )


    return {

        "message":
            "Wallet credited successfully",

        "new_balance":
            new_balance,

        "transaction":
            transaction.data
    }


# ============================================================
# WITHDRAW MONEY
#
# Works with:
#
# Farmer wallets
# Supplier wallets
#
# POST /api/marketplace/wallet/withdraw
#
# The WithdrawalCreate schema still uses farmer_id for
# backward compatibility. We use that value as the seller ID
# when looking up the wallet.
# ============================================================

@router.post("/wallet/withdraw")
async def withdraw(
    data: WithdrawalCreate
):

    # ========================================================
    # GET WALLET
    #
    # First search by seller_id.
    #
    # This allows supplier wallets to withdraw because supplier
    # wallets have:
    #
    # seller_id = supplier UUID
    # seller_type = supplier
    # farmer_id = NULL
    #
    # Then fall back to farmer_id for older farmer wallets.
    # ========================================================

    wallet_response = (
        supabase
        .table("wallets")
        .select("*")
        .eq(
            "seller_id",
            data.farmer_id
        )
        .execute()
    )


    wallet = None


    if wallet_response.data:

        wallet = wallet_response.data[0]


    # --------------------------------------------------------
    # FALLBACK FOR OLD FARMER WALLETS
    # --------------------------------------------------------

    if wallet is None:

        old_wallet_response = (
            supabase
            .table("wallets")
            .select("*")
            .eq(
                "farmer_id",
                data.farmer_id
            )
            .execute()
        )


        if old_wallet_response.data:

            wallet = old_wallet_response.data[0]


    # --------------------------------------------------------
    # WALLET NOT FOUND
    # --------------------------------------------------------

    if wallet is None:

        raise HTTPException(
            status_code=404,
            detail="Wallet not found"
        )


    # ========================================================
    # WALLET DETAILS
    # ========================================================

    balance = float(
        wallet.get("balance")
        or 0
    )


    seller_id = (
        wallet.get("seller_id")
        or data.farmer_id
    )


    seller_type = (
        wallet.get("seller_type")
        or "farmer"
    )


    # ========================================================
    # CHECK AMOUNT
    # ========================================================

    amount = float(
        data.amount
    )


    if amount <= 0:

        raise HTTPException(
            status_code=400,
            detail="Withdrawal amount must be greater than zero"
        )


    if amount > balance:

        raise HTTPException(
            status_code=400,
            detail="Insufficient balance"
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

    response = (
        supabase
        .table("withdrawals")
        .insert({

            "farmer_id":
                data.farmer_id,

            "amount":
                amount,

            "phone_number":
                data.mobile_number,

            "provider":
                data.network,

            "transaction_id":
                transaction_id,

            "status":
                "processing",

            "created_at":
                now
        })
        .execute()
    )


    if not response.data:

        raise HTTPException(
            status_code=500,
            detail="Failed to create withdrawal record."
        )


    # ========================================================
    # SEND MOBILE MONEY
    # ========================================================

    try:

        mtn = transfer_money(

            amount=amount,

            phone_number=
                data.mobile_number,

            external_id=
                transaction_id
        )


        if mtn.status_code not in [
            200,
            202
        ]:

            raise Exception(
                mtn.text
            )


        # ====================================================
        # UPDATE WALLET BALANCE
        # ====================================================

        new_balance = (
            balance -
            amount
        )


        wallet_update = (
            supabase
            .table("wallets")
            .update({

                "balance":
                    new_balance,

                "updated_at":
                    datetime.utcnow().isoformat()

            })
        )


        # ----------------------------------------------------
        # Update using wallet ID when available.
        # ----------------------------------------------------

        if wallet.get("id") is not None:

            wallet_update = wallet_update.eq(
                "id",
                wallet["id"]
            )

        else:

            wallet_update = wallet_update.eq(
                "seller_id",
                seller_id
            )


        wallet_update.execute()


        # ====================================================
        # CREATE DEBIT TRANSACTION
        #
        # This is the important addition.
        #
        # Withdrawals now appear in the transaction history.
        # ====================================================

        transaction = (
            supabase
            .table("transactions")
            .insert({

                "farmer_id":
                    data.farmer_id
                    if seller_type == "farmer"
                    else None,

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
                    "Mobile money withdrawal",

                "created_at":
                    now
            })
            .execute()
        )


        # ====================================================
        # MARK WITHDRAWAL COMPLETED
        # ====================================================

        supabase \
            .table("withdrawals") \
            .update({

                "status":
                    "completed"

            }) \
            .eq(
                "transaction_id",
                transaction_id
            ) \
            .execute()


        # ====================================================
        # RESPONSE
        # ====================================================

        return {

            "message":
                "Withdrawal completed successfully",

            "new_balance":
                new_balance,

            "withdrawal":
                response.data,

            "transaction":
                transaction.data
        }


    # ========================================================
    # WITHDRAWAL FAILED
    # ========================================================

    except Exception as e:

        supabase \
            .table("withdrawals") \
            .update({

                "status":
                    "failed"

            }) \
            .eq(
                "transaction_id",
                transaction_id
            ) \
            .execute()


        raise HTTPException(

            status_code=500,

            detail=str(e)
        )


# ============================================================
# FARMER TRANSACTIONS
#
# Existing endpoint retained.
#
# GET /api/marketplace/transactions/{farmer_id}
#
# Includes:
#
# - Marketplace earnings
# - Wallet credits
# - Wallet withdrawals
# ============================================================

@router.get("/transactions/{farmer_id}")
async def transactions(
    farmer_id: str
):

    response = (
        supabase
        .table("transactions")
        .select("*")
        .eq(
            "farmer_id",
            farmer_id
        )
        .order(
            "created_at",
            desc=True
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
#
# Optional:
#
# ?seller_type=farmer
# ?seller_type=supplier
#
# This is the endpoint the SupplierWalletScreen should use.
# ============================================================

@router.get("/transactions/seller/{seller_id}")
async def seller_transactions(
    seller_id: str,
    seller_type: str | None = None
):

    query = (
        supabase
        .table("transactions")
        .select("*")
        .eq(
            "seller_id",
            seller_id
        )
    )


    if seller_type:

        seller_type = seller_type.lower()


        if seller_type not in [
            "farmer",
            "supplier"
        ]:

            raise HTTPException(
                status_code=400,
                detail="Invalid seller type."
            )


        query = query.eq(
            "seller_type",
            seller_type
        )


    response = (
        query
        .order(
            "created_at",
            desc=True
        )
        .execute()
    )


    return response.data

