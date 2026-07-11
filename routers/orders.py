from fastapi import APIRouter, HTTPException

from database import supabase

from schemas.order import OrderCreate

from datetime import datetime


router = APIRouter()



# =====================================
# CREATE ORDER (BUY PRODUCT)
# POST /api/marketplace/orders
# =====================================

@router.post("/orders")
async def create_order(
    order: OrderCreate
):


    product_response = (

        supabase

        .table("products")

        .select("*")

        .eq(
            "id",
            order.product_id
        )

        .execute()

    )


    if not product_response.data:

        raise HTTPException(

            status_code=404,

            detail="Product not found"

        )


    product = product_response.data[0]



    total_amount = (

        order.quantity *

        product["price_per_unit"]

    )



    new_order = {


        "buyer_id":

        order.buyer_id,


        "farmer_id":

        product["farmer_id"],


        "product_id":

        order.product_id,


        "quantity":

        order.quantity,


        "total_amount":

        total_amount,


        "payment_status":

        "pending",


        "order_status":

        "placed",


        "status":

        "pending",


        "created_at":

        datetime.utcnow().isoformat()

    }



    response = (

        supabase

        .table("orders")

        .insert(new_order)

        .execute()

    )



    return {


        "message":

        "Order created successfully",


        "order":

        response.data

    }





# =====================================
# GET FARMER ORDERS
# =====================================

@router.get("/orders/farmer/{farmer_id}")
async def farmer_orders(

    farmer_id: str

):


    response = (

        supabase

        .table("orders")

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





# =====================================
# GET BUYER ORDERS
# =====================================

@router.get("/orders/buyer/{buyer_id}")
async def buyer_orders(

    buyer_id: str

):


    response = (

        supabase

        .table("orders")

        .select("*")

        .eq(

            "buyer_id",

            buyer_id

        )

        .order(

            "created_at",

            desc=True

        )

        .execute()

    )


    return response.data





# =====================================
# COMPLETE ORDER AND PAY FARMER
# =====================================

@router.put("/orders/{order_id}/complete")
async def complete_order(

    order_id: str

):


    order_response = (

        supabase

        .table("orders")

        .select("*")

        .eq(

            "id",

            order_id

        )

        .execute()

    )



    if not order_response.data:


        raise HTTPException(

            status_code=404,

            detail="Order not found"

        )



    order = order_response.data[0]





    # Update order status

    supabase.table("orders").update({


        "status":

        "completed",


        "order_status":

        "completed",


        "payment_status":

        "paid"


    }).eq(

        "id",

        order_id

    ).execute()





    # Create transaction

    transaction = {


        "farmer_id":

        order["farmer_id"],


        "amount":

        order["total_amount"],


        "type":

        "sale",


        "created_at":

        datetime.utcnow().isoformat()

    }



    supabase.table("transactions").insert(

        transaction

    ).execute()





    # Get farmer wallet

    wallet_response = (

        supabase

        .table("wallets")

        .select("*")

        .eq(

            "farmer_id",

            order["farmer_id"]

        )

        .execute()

    )





    if wallet_response.data:


        wallet = wallet_response.data[0]


        current_balance = (

            wallet["balance"]

            or 0

        )


        new_balance = (

            current_balance +

            order["total_amount"]

        )



        supabase.table("wallets").update({


            "balance":

            new_balance,


            "updated_at":

            datetime.utcnow().isoformat()


        }).eq(

            "farmer_id",

            order["farmer_id"]

        ).execute()




    else:


        supabase.table("wallets").insert({


            "farmer_id":

            order["farmer_id"],


            "balance":

            order["total_amount"],


            "currency":

            "UGX",


            "updated_at":

            datetime.utcnow().isoformat()


        }).execute()





    return {


        "message":

        "Order completed and farmer paid",


        "amount":

        order["total_amount"]


    }





# =====================================
# UPDATE ORDER STATUS
# =====================================

@router.put("/orders/{order_id}")
async def update_order(

    order_id: str,

    status: str

):


    response = (

        supabase

        .table("orders")

        .update({


            "status":

            status


        })

        .eq(

            "id",

            order_id

        )

        .execute()

    )


    return {


        "message":

        "Order status updated",


        "order":

        response.data

    }
