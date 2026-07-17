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
# GET /api/marketplace/wallet/{farmer_id}
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


        "farmer_id":

        farmer_id,


        "balance":

        0,


        "currency":

        "UGX"

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
# POST /api/marketplace/wallet/create
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
# POST /api/marketplace/wallet/earn
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
# WITHDRAW MONEY
# POST /api/marketplace/wallet/withdraw
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






    withdrawal = {

    "farmer_id": data.farmer_id,

    "amount": data.amount,

    "phone_number": data.mobile_number,

    "provider": data.network,

    "status": "processing",

    "transaction_id": None,

    "created_at": datetime.utcnow().isoformat()

}


        

        


        

        


        

        


        

        


        

        


        

        

    





    response = (

        supabase

        .table("withdrawals")

        .insert(withdrawal)

        .execute()

    )





    new_balance = balance - data.amount





    supabase.table("wallets").update({


        "balance":

        new_balance,


        "updated_at":

        datetime.utcnow().isoformat()


    }).eq(


        "farmer_id",

        data.farmer_id


    ).execute()





    return {


        "message":

        "Withdrawal request submitted",



        "withdrawal":

        response.data

    }









# =====================================
# GET FARMER TRANSACTIONS
# GET /api/marketplace/transactions/{farmer_id}
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
