from fastapi import APIRouter, HTTPException

from database import supabase

from schemas.wallet import (
    WalletCreate,
    WithdrawalCreate
)

from datetime import datetime



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

        .single()

        .execute()

    )


    if not response.data:

        raise HTTPException(

            status_code=404,

            detail="Wallet not found"

        )


    return response.data





# =====================================
# CREATE FARMER WALLET
# =====================================


@router.post("/wallet/create")
async def create_wallet(
    wallet: WalletCreate
):


    new_wallet = {

        "farmer_id":
        wallet.farmer_id,


        "balance":
        wallet.amount

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
        response.data

    }





# =====================================
# ADD FARMER EARNINGS
# =====================================


@router.post("/wallet/earn")
async def add_money(
    data: WalletCreate
):


    # Add transaction record

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




    # Update wallet balance

    wallet_response = (

        supabase

        .table("wallets")

        .select("balance")

        .eq(
            "farmer_id",
            data.farmer_id
        )

        .single()

        .execute()

    )



    if wallet_response.data:


        current_balance = (

            wallet_response.data["balance"]

            or 0

        )


        new_balance = (

            current_balance +

            data.amount

        )



        supabase.table("wallets").update({

            "balance":
            new_balance

        }).eq(

            "farmer_id",

            data.farmer_id

        ).execute()





    return {


        "message":

        "Payment received and wallet updated",


        "transaction":

        transaction_response.data

    }





# =====================================
# WITHDRAW MONEY
# =====================================


@router.post("/wallet/withdraw")
async def withdraw(
    data: WithdrawalCreate
):


    withdrawal = {


        "farmer_id":

        data.farmer_id,


        "amount":

        data.amount,


        "phone":

        data.mobile_number,


        "provider":

        data.network,


        "status":

        "processing",


        "created_at":

        datetime.utcnow().isoformat()

    }



    response = (

        supabase

        .table("withdrawals")

        .insert(withdrawal)

        .execute()

    )



    return {


        "message":

        "Withdrawal request submitted",


        "withdrawal":

        response.data

    }
