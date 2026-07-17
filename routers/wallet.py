from fastapi import APIRouter, HTTPException

from database import supabase

from schemas.wallet import (
    WalletCreate,
    WithdrawalCreate
)

from services.mtn_service import transfer_money

from datetime import datetime

import uuid



router = APIRouter()





# =====================================
# GET FARMER WALLET
# =====================================

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



    new_wallet = {

        "farmer_id": farmer_id,

        "balance": 0,

        "currency": "UGX"

    }



    created_wallet = (

        supabase
        .table("wallets")
        .insert(new_wallet)
        .execute()

    )


    return created_wallet.data[0]









# =====================================
# CREATE FARMER WALLET
# =====================================

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




    new_wallet = {

        "farmer_id":
        wallet.farmer_id,

        "balance":
        wallet.amount,

        "currency":
        "UGX"

    }



    response = (

        supabase
        .table("wallets")
        .insert(new_wallet)
        .execute()

    )



    return {

        "message":
        "Wallet created successfully",

        "wallet":
        response.data[0]

    }









# =====================================
# ADD FARMER EARNINGS
# =====================================

@router.post("/wallet/earn")
async def add_money(
    data: WalletCreate
):


    transaction = {

        "farmer_id":
        data.farmer_id,

        "amount":
        data.amount,

        "type":
        "sale",

        "created_at":
        datetime.utcnow().isoformat()

    }




    transaction_response = (

        supabase
        .table("transactions")
        .insert(transaction)
        .execute()

    )




    wallet_response = (

        supabase
        .table("wallets")
        .select("*")
        .eq(
            "farmer_id",
            data.farmer_id
        )
        .execute()

    )




    if wallet_response.data:


        wallet = wallet_response.data[0]


        current_balance = (

            wallet.get("balance")
            or 0

        )


        new_balance = (

            current_balance
            + data.amount

        )



        supabase.table("wallets").update({

            "balance":
            new_balance,

            "updated_at":
            datetime.utcnow().isoformat()

        }).eq(

            "farmer_id",
            data.farmer_id

        ).execute()



    else:


        supabase.table("wallets").insert({

            "farmer_id":
            data.farmer_id,

            "balance":
            data.amount,

            "currency":
            "UGX"

        }).execute()





    return {

        "message":
        "Payment received and wallet updated",

        "transaction":
        transaction_response.data

    }









# =====================================
# WITHDRAW MONEY + MTN DISBURSEMENT
# =====================================

@router.post("/wallet/withdraw")
async def withdraw(
    data: WithdrawalCreate
):


    wallet_response = (

        supabase
        .table("wallets")
        .select("*")
        .eq(
            "farmer_id",
            data.farmer_id
        )
        .execute()

    )



    if not wallet_response.data:


        raise HTTPException(

            status_code=404,

            detail="Wallet not found"

        )




    wallet = wallet_response.data[0]


    balance = wallet.get("balance") or 0





    if data.amount > balance:


        raise HTTPException(

            status_code=400,

            detail="Insufficient wallet balance"

        )





    # Generate MTN transaction reference

    transaction_id = str(
        uuid.uuid4()
    )





    # Save withdrawal request

    withdrawal = {


        "farmer_id":
        data.farmer_id,


        "amount":
        data.amount,


        "phone_number":
        data.mobile_number,


        "provider":
        data.network,


        "status":
        "processing",


        "transaction_id":
        transaction_id,


        "created_at":
        datetime.utcnow().isoformat()

    }





    response = (

        supabase
        .table("withdrawals")
        .insert(withdrawal)
        .execute()

    )





    try:


        # =====================================
        # SEND MONEY THROUGH MTN
        # =====================================


        mtn_response = transfer_money(

            amount=data.amount,

            phone_number=data.mobile_number,

            external_id=transaction_id

        )




        if mtn_response.status_code in [200,202]:

            
            supabase.table("withdrawals").update({

                "status":
                "processing"

            }).eq(

                "transaction_id",
                transaction_id

            ).execute()



        else:


            raise Exception(
                mtn_response.text
            )





    except Exception as e:



        # MTN failed
        # Refund wallet


        supabase.table("withdrawals").update({

            "status":
            "failed"

        }).eq(

            "transaction_id",
            transaction_id

        ).execute()





        supabase.table("wallets").update({

            "balance":
            balance,

            "updated_at":
            datetime.utcnow().isoformat()


        }).eq(

            "farmer_id",
            data.farmer_id

        ).execute()



        raise HTTPException(

            status_code=500,

            detail=f"MTN payout failed: {str(e)}"

        )





    # Deduct wallet only after MTN request accepted

    supabase.table("wallets").update({

        "balance":
        balance - data.amount,


        "updated_at":
        datetime.utcnow().isoformat()


    }).eq(

        "farmer_id",
        data.farmer_id

    ).execute()





    return {


        "message":
        "Withdrawal sent to MTN successfully",


        "withdrawal":
        response.data

    }









# =====================================
# GET FARMER TRANSACTIONS
# =====================================

@router.get("/transactions/{farmer_id}")
async def farmer_transactions(

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
