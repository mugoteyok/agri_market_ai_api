from fastapi import APIRouter
from database import supabase
from datetime import datetime


router = APIRouter()



# ===============================
# CREATE ORDER
# ===============================


@router.post("/orders")
async def create_order(data:dict):


    order={


        "buyer_id":
        data["buyer_id"],


        "farmer_id":
        data["farmer_id"],


        "product_id":
        data["product_id"],


        "quantity":
        data["quantity"],


        "amount":
        data["amount"],


        "status":
        "pending",


        "created_at":
        datetime.utcnow()

    }



    response=(

        supabase
        .table("orders")
        .insert(order)
        .execute()

    )


    return {

        "message":
        "Order created",

        "order":
        response.data

    }



# ===============================
# UPDATE ORDER STATUS
# ===============================


@router.put("/orders/{order_id}")

async def update_order(
    order_id:str,
    status:str
):


    response=(

        supabase
        .table("orders")
        .update({

            "status":status

        })

        .eq(
            "id",
            order_id
        )

        .execute()

    )


    return response.data
