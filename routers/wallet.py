from fastapi import APIRouter, HTTPException

from database import supabase

from schemas.wallet import (
    WalletCreate,
    WalletEarning,
    WithdrawalCreate,
)

from services.mtn_service import (
    transfer_money,
    get_transfer_status,
)

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
#
# IMPORTANT:
#
# This endpoint DOES NOT immediately mark the withdrawal
# completed.
#
# MTN disbursements are asynchronous.
#
# The withdrawal remains:
#
#     processing
#
# until the confirmation endpoint verifies that MTN reports:
#
#     SUCCESSFUL
#
# The wallet is only deducted after SUCCESSFUL confirmation.
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
    #
    # IMPORTANT:
    #
    # The withdrawal now permanently stores:
    #
    #     seller_id
    #     seller_type
    #
    # This allows the confirmation endpoint to identify
    # both farmers and suppliers directly.
    #
    # mtn_reference_id is NOT known yet.
    #
    # It will be saved immediately after MTN accepts
    # the transfer.
    # ========================================================

    withdrawal_data = {

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

        "phone_number":
            phone_number,

        "provider":
            data.network.value,

        "transaction_id":
            transaction_id,

        "mtn_reference_id":
            None,

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
    #
    # MTN DISBURSEMENT
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

            print(
                "MTN TRANSFER NOT ACCEPTED"
            )

            print(
                "status_code:",
                status_code,
            )

            print(
                "response:",
                response_text,
            )

            # ------------------------------------------------
            # MTN DID NOT ACCEPT THE TRANSFER.
            #
            # Therefore no wallet deduction.
            # ------------------------------------------------

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
                    "Mobile Money withdrawal was "
                    "not accepted by MTN."
                ),
            )

        # ====================================================
        # GET MTN REFERENCE
        # ====================================================

        mtn_reference_id = (
            mtn_response.get(
                "reference_id"
            )
        )

        if not mtn_reference_id:

            print(
                "CRITICAL: MTN accepted transfer "
                "but returned no reference ID."
            )

            raise HTTPException(
                status_code=500,
                detail=(
                    "MTN accepted the withdrawal but "
                    "did not return a transfer reference. "
                    "The withdrawal requires reconciliation."
                ),
            )

        # ====================================================
        # SAVE MTN REFERENCE
        #
        # THIS FIXES:
        #
        # mtn_reference_id = null
        # ====================================================

        reference_update = (
            supabase
            .table("withdrawals")
            .update({
                "mtn_reference_id":
                    mtn_reference_id,

                "status":
                    "processing",
            })
            .eq(
                "transaction_id",
                transaction_id,
            )
            .execute()
        )

        if not reference_update.data:

            print(
                "CRITICAL: MTN transfer accepted but "
                "mtn_reference_id could not be saved."
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
                    "Mobile Money transfer was accepted, "
                    "but the MTN reference could not be "
                    "saved. The withdrawal requires "
                    "reconciliation."
                ),
            )

        # ====================================================
        # LOG ACCEPTED TRANSFER
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
            "status: processing",
        )

        print(
            "================================================"
        )

        # ====================================================
        # IMPORTANT
        #
        # DO NOT DEDUCT THE WALLET HERE.
        #
        # HTTP 202 means MTN accepted the request.
        #
        # We wait for get_transfer_status().
        # ====================================================

        return {

            "message":
                "Withdrawal request accepted and is "
                "being processed by Mobile Money.",

            "status":
                "processing",

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
                balance,

            "transaction_id":
                transaction_id,

            "mtn_reference_id":
                mtn_reference_id,

            "withdrawal":
                reference_update.data,

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
# CONFIRM WITHDRAWAL STATUS
#
# GET /api/marketplace/wallet/withdraw/{transaction_id}/status
#
# This endpoint checks the REAL MTN disbursement status.
#
# IMPORTANT:
#
# The wallet is deducted ONLY when MTN says:
#
#     SUCCESSFUL
#
# PENDING:
#
#     wallet remains unchanged
#
# FAILED:
#
#     wallet remains unchanged
# ============================================================

@router.get(
    "/wallet/withdraw/{transaction_id}/status"
)
async def confirm_withdrawal(
    transaction_id: str,
):

    # ========================================================
    # FIND WITHDRAWAL
    # ========================================================

    withdrawal_response = (
        supabase
        .table("withdrawals")
        .select("*")
        .eq(
            "transaction_id",
            transaction_id,
        )
        .limit(1)
        .execute()
    )

    if not withdrawal_response.data:

        raise HTTPException(
            status_code=404,
            detail="Withdrawal not found.",
        )

    withdrawal = (
        withdrawal_response.data[0]
    )

    # ========================================================
    # READ CURRENT STATUS
    # ========================================================

    current_status = (
        withdrawal.get("status")
        or ""
    ).strip().lower()

    # ========================================================
    # ALREADY COMPLETED
    #
    # Prevent duplicate wallet deduction.
    # ========================================================

    if current_status == "completed":

        return {

            "message":
                "Withdrawal already completed.",

            "status":
                "completed",

            "transaction_id":
                transaction_id,

            "mtn_reference_id":
                withdrawal.get(
                    "mtn_reference_id"
                ),

            "amount":
                withdrawal.get(
                    "amount"
                ),

        }

    # ========================================================
    # ALREADY FAILED
    #
    # Prevent unnecessary repeated processing.
    # ========================================================

    if current_status == "failed":

        return {

            "message":
                "Withdrawal has already failed.",

            "status":
                "failed",

            "transaction_id":
                transaction_id,

            "mtn_reference_id":
                withdrawal.get(
                    "mtn_reference_id"
                ),

            "amount":
                withdrawal.get(
                    "amount"
                ),

        }

    # ========================================================
    # GET MTN REFERENCE
    # ========================================================

    mtn_reference_id = (
        withdrawal.get(
            "mtn_reference_id"
        )
    )

    if not mtn_reference_id:

        raise HTTPException(
            status_code=500,
            detail=(
                "Withdrawal is missing its MTN "
                "transfer reference."
            ),
        )

    # ========================================================
    # ASK MTN FOR REAL TRANSFER STATUS
    # ========================================================

    try:

        mtn_status = get_transfer_status(
            mtn_reference_id
        )

    except Exception as e:

        print(
            "MTN TRANSFER STATUS CHECK ERROR:",
            str(e),
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "Unable to confirm Mobile Money "
                "withdrawal status at this time."
            ),
        )

    # ========================================================
    # READ MTN STATUS
    # ========================================================

    transfer_status = (
        mtn_status.get("status")
        or ""
    ).strip().upper()

    print(
        "================================================"
    )

    print(
        "MTN WITHDRAWAL STATUS CHECK"
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
        "mtn_status:",
        transfer_status,
    )

    print(
        "MTN RESPONSE:",
        mtn_status,
    )

    print(
        "================================================"
    )

    # ========================================================
    # MTN FAILED
    # ========================================================

    if transfer_status in [
        "FAILED",
        "FAILURE",
    ]:

        failed_response = (
            supabase
            .table("withdrawals")
            .update({
                "status": "failed",
            })
            .eq(
                "transaction_id",
                transaction_id,
            )
            .eq(
                "status",
                "processing",
            )
            .execute()
        )

        return {

            "message":
                "Mobile Money withdrawal failed.",

            "status":
                "failed",

            "transaction_id":
                transaction_id,

            "mtn_reference_id":
                mtn_reference_id,

            "amount":
                withdrawal.get(
                    "amount"
                ),

            "withdrawal":
                failed_response.data,

            "mtn_response":
                mtn_status,

        }

    # ========================================================
    # MTN STILL PROCESSING
    # ========================================================

    if transfer_status in [
        "PENDING",
        "PROCESSING",
        "ACCEPTED",
    ]:

        return {

            "message":
                "Mobile Money withdrawal is still "
                "being processed.",

            "status":
                "processing",

            "transaction_id":
                transaction_id,

            "mtn_reference_id":
                mtn_reference_id,

            "amount":
                withdrawal.get(
                    "amount"
                ),

            "mtn_response":
                mtn_status,

        }

    # ========================================================
    # MTN SUCCESSFUL
    # ========================================================

    if transfer_status == "SUCCESSFUL":

        # ====================================================
        # CHECK WHETHER FINANCIAL TRANSACTION ALREADY EXISTS
        #
        # Prevent duplicate wallet deductions.
        # ====================================================

        existing_transaction = (
            supabase
            .table("transactions")
            .select("*")
            .eq(
                "reference_id",
                transaction_id,
            )
            .eq(
                "type",
                "debit",
            )
            .limit(1)
            .execute()
        )

        # ----------------------------------------------------
        # If a transaction already exists, the withdrawal was
        # already financially processed.
        # ----------------------------------------------------

        if existing_transaction.data:

            transaction = (
                existing_transaction.data[0]
            )

            completed = (
                supabase
                .table("withdrawals")
                .update({
                    "status": "completed",
                })
                .eq(
                    "transaction_id",
                    transaction_id,
                )
                .eq(
                    "status",
                    "processing",
                )
                .execute()
            )

            return {

                "message":
                    "Withdrawal was already financially "
                    "processed.",

                "status":
                    "completed",

                "transaction_id":
                    transaction_id,

                "mtn_reference_id":
                    mtn_reference_id,

                "transaction":
                    transaction,

                "withdrawal":
                    completed.data,

            }

        # ====================================================
        # DETERMINE SELLER DIRECTLY FROM WITHDRAWAL
        #
        # Every new withdrawal now stores:
        #
        #     seller_id
        #     seller_type
        #
        # This works for BOTH:
        #
        #     farmer
        #     supplier
        #
        # ====================================================

        seller_id = withdrawal.get(
            "seller_id"
        )

        seller_type = (
            withdrawal.get("seller_type")
            or ""
        ).strip().lower()

        # ----------------------------------------------------
        # FALLBACK FOR OLD FARMER WITHDRAWALS
        #
        # Existing withdrawals created before this update may
        # only have farmer_id.
        # ----------------------------------------------------

        if not seller_id:

            farmer_id = withdrawal.get(
                "farmer_id"
            )

            if farmer_id:

                seller_id = farmer_id
                seller_type = "farmer"

        # ----------------------------------------------------
        # VALIDATE SELLER INFORMATION
        # ----------------------------------------------------

        if not seller_id:

            raise HTTPException(
                status_code=409,
                detail=(
                    "Withdrawal does not contain a seller ID. "
                    "Manual reconciliation is required."
                ),
            )

        if seller_type not in [
            "farmer",
            "supplier",
        ]:

            raise HTTPException(
                status_code=409,
                detail=(
                    "Withdrawal contains an invalid seller type. "
                    "Manual reconciliation is required."
                ),
            )

        print(
            "WITHDRAWAL SELLER:",
            seller_id,
            seller_type,
        )

        # ====================================================
        # FIND EXACT SELLER WALLET
        # ====================================================

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

        # ====================================================
        # WALLET MUST EXIST
        # ====================================================

        if not wallet_response.data:

            raise HTTPException(
                status_code=404,
                detail=(
                    f"{seller_type.capitalize()} "
                    "wallet not found during withdrawal "
                    "confirmation."
                ),
            )

        wallet = wallet_response.data[0]

        wallet_id = wallet.get(
            "id"
        )

        balance = float(
            wallet.get("balance")
            or 0
        )

        amount = float(
            withdrawal.get("amount")
            or 0
        )

        # ====================================================
        # CHECK BALANCE AGAIN
        #
        # Never allow a negative balance.
        # ====================================================

        if amount > balance:

            raise HTTPException(
                status_code=409,
                detail=(
                    "MTN confirmed the withdrawal, but the "
                    "seller wallet no longer has enough balance "
                    "to reconcile this withdrawal. Manual "
                    "reconciliation is required."
                ),
            )

        # ====================================================
        # CALCULATE NEW BALANCE
        # ====================================================

        new_balance = (
            balance
            - amount
        )

        # ====================================================
        # DEDUCT EXACT WALLET
        #
        # IMPORTANT:
        #
        # We also require the current balance to still equal
        # the balance we read.
        #
        # This helps prevent the same withdrawal from being
        # deducted twice by simultaneous confirmation requests.
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
            .eq(
                "balance",
                balance,
            )
            .execute()
        )

        # ====================================================
        # WALLET UPDATE FAILED
        # ====================================================

        if not wallet_update_response.data:

            print(
                "CRITICAL: MTN payout successful but "
                "wallet deduction failed."
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
                "seller_id:",
                seller_id,
            )

            print(
                "seller_type:",
                seller_type,
            )

            raise HTTPException(
                status_code=500,
                detail=(
                    "Mobile Money payout was successful, "
                    "but the seller wallet could not be "
                    "updated. Manual reconciliation is "
                    "required."
                ),
            )

        # ====================================================
        # CREATE DEBIT TRANSACTION
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
                    datetime.utcnow().isoformat(),

            })
            .execute()
        )

        # ====================================================
        # TRANSACTION INSERT FAILED
        # ====================================================

        if not transaction_response.data:

            print(
                "CRITICAL: Wallet was deducted after "
                "successful MTN payout, but debit transaction "
                "could not be created."
            )

            print(
                "transaction_id:",
                transaction_id,
            )

            print(
                "seller_id:",
                seller_id,
            )

            print(
                "seller_type:",
                seller_type,
            )

            raise HTTPException(
                status_code=500,
                detail=(
                    "Withdrawal payout was successful and "
                    "wallet was deducted, but the transaction "
                    "record could not be created. Manual "
                    "reconciliation is required."
                ),
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
            .eq(
                "status",
                "processing",
            )
            .execute()
        )

        # ====================================================
        # RETURN SUCCESS
        # ====================================================

        return {

            "message":
                "Withdrawal completed successfully.",

            "status":
                "completed",

            "seller_id":
                seller_id,

            "seller_type":
                seller_type,

            "amount":
                amount,

            "mobile_number":
                withdrawal.get(
                    "phone_number"
                ),

            "provider":
                withdrawal.get(
                    "provider"
                ),

            "previous_balance":
                balance,

            "new_balance":
                new_balance,

            "transaction_id":
                transaction_id,

            "mtn_reference_id":
                mtn_reference_id,

            "withdrawal":
                completed_withdrawal.data,

            "transaction":
                transaction_response.data,

            "mtn_response":
                mtn_status,

        }

    # ========================================================
    # UNKNOWN MTN STATUS
    # ========================================================

    return {

        "message":
            "MTN returned an unrecognized transfer status.",

        "status":
            "processing",

        "transaction_id":
            transaction_id,

        "mtn_reference_id":
            mtn_reference_id,

        "amount":
            withdrawal.get(
                "amount"
            ),

        "mtn_status":
            transfer_status,

        "mtn_response":
            mtn_status,

    }


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
