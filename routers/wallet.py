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





# =====================================
# GET WALLET
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



    wallet = {

        "farmer_id":

        farmer_id,


        "balance":

        0,


        "currency":

        "UGX"

    }



    created = (

        supabase

        .table("wallets")

        .insert(wallet)

        .execute()

    )



    return created.data[0]







# =====================================
# CREATE WALLET
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






    response = (

        supabase

        .table("wallets")

        .insert({

            "farmer_id":

            wallet.farmer_id,


            "balance":

            0,


            "currency":

            "UGX"

        })

        .execute()

    )




    return response.data[0]







# =====================================
# CREDIT FARMER WALLET
# MARKETPLACE ORDER PAYMENT
# =====================================


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





    # Create wallet if missing

    if not wallet.data:


        supabase

        .table("wallets")

        .insert({

            "farmer_id":

            data.farmer_id,


            "balance":

            0,


            "currency":

            "UGX"

        })

        .execute()



        current_balance = 0



    else:


        current_balance = (

            wallet.data[0]["balance"]

            or

            0

        )







    new_balance = (

        current_balance

        +

        data.amount

    )







    # Update wallet balance


    supabase.table("wallets").update({

        "balance":

        new_balance

    }).eq(

        "farmer_id",

        data.farmer_id

    ).execute()







    # Save earning transaction


    transaction = (

        supabase

        .table("transactions")

        .insert({

            "farmer_id":

            data.farmer_id,


            "amount":

            data.amount,


            "type":

            "credit",


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








# =====================================
# WITHDRAW MONEY
# =====================================


@router.post("/wallet/withdraw")
async def withdraw(

    data: WithdrawalCreate

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




    if not wallet.data:


        raise HTTPException(

            status_code=404,

            detail="Wallet not found"

        )





    balance = (

        wallet.data[0]["balance"]

        or

        0

    )






    if data.amount > balance:


        raise HTTPException(

            status_code=400,

            detail="Insufficient balance"

        )







    transaction_id = str(uuid.uuid4())







    response = (

        supabase

        .table("withdrawals")

        .insert({

            "farmer_id":

            data.farmer_id,


            "amount":

            data.amount,


            "phone_number":

            data.mobile_number,


            "provider":

            data.network,


            "transaction_id":

            transaction_id,


            "status":

            "processing",


            "created_at":

            datetime.utcnow().isoformat()

        })

        .execute()

    )







    try:


        mtn = transfer_money(

            amount=data.amount,

            phone_number=data.mobile_number,

            external_id=transaction_id

        )




        if mtn.status_code not in [200, 202]:

            raise Exception(mtn.text)







        supabase.table("wallets").update({

            "balance":

            balance - data.amount

        }).eq(

            "farmer_id",

            data.farmer_id

        ).execute()







        return {


            "message":

            "Withdrawal processing",


            "withdrawal":

            response.data

        }






    except Exception as e:


        supabase.table("withdrawals").update({

            "status":

            "failed"

        }).eq(

            "transaction_id",

            transaction_id

        ).execute()






        raise HTTPException(

            status_code=500,

            detail=str(e)

        )








# =====================================
# TRANSACTIONS
# =====================================


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
