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


    # Get product details

    product_response = (

        supabase

        .table("products")

        .select("*")

        .eq(

            "id",

            order.product_id

        )

        .single()

        .execute()

    )


    product = product_response.data



    if not product:


        raise HTTPException(

            status_code=404,

            detail="Product not found"

        )



    # Calculate total amount

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


        "amount":

        total_amount,


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
# GET /api/marketplace/orders/farmer/{farmer_id}
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
# GET /api/marketplace/orders/buyer/{buyer_id}
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
# PUT /api/marketplace/orders/{order_id}/complete
# =====================================


@router.put("/orders/{order_id}/complete")
async def complete_order(

    order_id: str

):


    # Find order

    order_response = (

        supabase

        .table("orders")

        .select("*")

        .eq(

            "id",

            order_id

        )

        .single()

        .execute()

    )



    order = order_response.data



    if not order:


        raise HTTPException(

            status_code=404,

            detail="Order not found"

        )



    # Mark order completed

    supabase.table("orders").update({

        "status":

        "completed"

    }).eq(

        "id",

        order_id

    ).execute()





    # Add transaction

    transaction = {


        "farmer_id":

        order["farmer_id"],


        "amount":

        order["amount"],


        "type":

        "sale",


        "created_at":

        datetime.utcnow().isoformat()

    }



    supabase.table("transactions").insert(

        transaction

    ).execute()





    # Update farmer wallet


    wallet_response = (

        supabase

        .table("wallets")

        .select("*")

        .eq(

            "farmer_id",

            order["farmer_id"]

        )

        .single()

        .execute()

    )




    if wallet_response.data:


        current_balance = (

            wallet_response.data.get("balance")

            or 0

        )


        new_balance = (

            current_balance +

            order["amount"]

        )



        supabase.table("wallets").update({

            "balance":

            new_balance

        }).eq(

            "farmer_id",

            order["farmer_id"]

        ).execute()



    else:


        supabase.table("wallets").insert({

            "farmer_id":

            order["farmer_id"],


            "balance":

            order["amount"]

        }).execute()





    return {


        "message":

        "Order completed and farmer paid",


        "amount":

        order["amount"]

    }





# =====================================
# UPDATE ORDER STATUS
# PUT /api/marketplace/orders/{order_id}
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
