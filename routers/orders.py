from fastapi import APIRouter, HTTPException

from database import supabase

from schemas.order import OrderCreate

from schemas.wallet import WalletEarning

from datetime import datetime


router = APIRouter()





# =====================================
# CREATE ORDER
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





    if order.quantity > product["quantity"]:


        raise HTTPException(

            status_code=400,

            detail="Insufficient product quantity"

        )





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


        "crop":

        product["crop"],


        "price_per_unit":

        product["price_per_unit"],


        "image_url":

        product.get("image_url"),


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






    order_response = (

        supabase

        .table("orders")

        .insert(new_order)

        .execute()

    )







    # Reduce stock


    remaining_quantity = (

        product["quantity"]

        -

        order.quantity

    )





    product_update = {


        "quantity":

        remaining_quantity

    }





    if remaining_quantity <= 0:


        product_update["status"] = "sold"





    supabase.table("products").update(

        product_update

    ).eq(

        "id",

        order.product_id

    ).execute()






    return {


        "message":

        "Order created successfully",


        "order":

        order_response.data

    }









# =====================================
# FARMER ORDERS
# =====================================


@router.get("/orders/farmer/{farmer_id}")
async def farmer_orders(

    farmer_id:str

):


    response=(

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
# BUYER ORDERS
# =====================================


@router.get("/orders/buyer/{buyer_id}")
async def buyer_orders(

    buyer_id:str

):


    response=(

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
# COMPLETE ORDER
# =====================================


@router.put("/orders/{order_id}/complete")
async def complete_order(

    order_id:str

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







    # Prevent duplicate payment


    if order["payment_status"] == "paid":


        raise HTTPException(

            status_code=400,

            detail="Order already completed"

        )








    # Update order


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







    # =====================================
    # CREDIT FARMER WALLET
    # =====================================


    wallet = (

        supabase

        .table("wallets")

        .select("*")

        .eq(

            "farmer_id",

            order["farmer_id"]

        )

        .execute()

    )





    if wallet.data:


        current_balance = (

            wallet.data[0]["balance"]

            or

            0

        )



        new_balance = (

            current_balance

            +

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

            "UGX"



        }).execute()







    # =====================================
    # CREATE TRANSACTION RECORD
    # =====================================


    supabase.table("transactions").insert({


        "farmer_id":

        order["farmer_id"],


        "amount":

        order["total_amount"],


        "type":

        "credit",


        "reference_id":

        order_id,


        "description":

        f"{order.get('crop')} marketplace sale",


        "created_at":

        datetime.utcnow().isoformat()



    }).execute()







    return {


        "message":

        "Order completed and farmer wallet credited",


        "order_id":

        order_id,


        "amount":

        order["total_amount"]

    }
