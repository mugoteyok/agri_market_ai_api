from fastapi import APIRouter
from database import supabase
from datetime import datetime


router = APIRouter()



# ===============================
# GET FARMER WALLET
# ===============================


@router.get("/wallet/{farmer_id}")

async def get_wallet(
    farmer_id:str
):


    response=(

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


    return response.data





# ===============================
# ADD EARNINGS
# ===============================


@router.post("/wallet/earn")

async def add_money(data:dict):


    transaction={


        "farmer_id":
        data["farmer_id"],


        "amount":
        data["amount"],


        "type":
        "sale",


        "created_at":
        datetime.utcnow()

    }


    response=(

        supabase
        .table("transactions")
        .insert(transaction)
        .execute()

    )


    return {

        "message":
        "Payment received",

        "data":
        response.data

    }





# ===============================
# WITHDRAW MONEY
# ===============================


@router.post("/wallet/withdraw")

async def withdraw(data:dict):


    withdrawal={


        "farmer_id":
        data["farmer_id"],


        "amount":
        data["amount"],


        "phone":
        data["phone"],


        "provider":
        data["provider"],


        "status":
        "processing"

    }



    response=(

        supabase
        .table("withdrawals")
        .insert(withdrawal)

        .execute()

    )



    return {


        "message":

        "Withdrawal request submitted",


        "data":

        response.data

  }
