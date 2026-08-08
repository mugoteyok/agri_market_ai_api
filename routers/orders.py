from fastapi import APIRouter, HTTPException

from database import supabase

from schemas.order import OrderCreate

from schemas.wallet import WalletEarning

from schemas.payment import PaymentRequest

from datetime import datetime


router = APIRouter()


# =====================================
# CREATE ORDER
# POST /api/marketplace/orders
#
# Works for:
# 🌾 Farmer → produce
# 🏪 Supplier → seeds, pesticides,
#    fertilizer, equipment, etc.
# =====================================

@router.post("/orders")
async def create_order(
    order: OrderCreate
):

    # ---------------------------------
    # GET PRODUCT
    # ---------------------------------

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


    # ---------------------------------
    # CHECK AVAILABILITY
    # ---------------------------------

    if product["status"] != "available":

        raise HTTPException(
            status_code=400,
            detail="Product is no longer available"
        )


    # ---------------------------------
    # CHECK QUANTITY
    # ---------------------------------

    if order.quantity <= 0:

        raise HTTPException(
            status_code=400,
            detail="Quantity must be greater than zero"
        )


    if order.quantity > product["quantity"]:

        raise HTTPException(
            status_code=400,
            detail="Insufficient product quantity"
        )


    # ---------------------------------
    # DETERMINE SELLER
    # ---------------------------------

    seller_id = (
        product.get("seller_id")
        or product.get("farmer_id")
    )

    seller_type = (
        product.get("seller_type")
        or "farmer"
    )

    product_type = (
        product.get("product_type")
        or "produce"
    )


    if not seller_id:

        raise HTTPException(
            status_code=400,
            detail="Product does not have a seller"
        )


    # ---------------------------------
    # PRICE
    # ---------------------------------

    price_per_unit = float(
        product["price_per_unit"]
    )

    quantity = float(
        order.quantity
    )

    total_amount = (
        quantity *
        price_per_unit
    )


    # ---------------------------------
    # FARMER COMPATIBILITY
    #
    # Existing farmer products/orders
    # continue to use farmer_id.
    #
    # Supplier products have farmer_id
    # set to NULL.
    # ---------------------------------

    farmer_id = None

    if seller_type == "farmer":

        farmer_id = seller_id


    # ---------------------------------
    # CREATE ORDER
    # ---------------------------------

    new_order = {

        "buyer_id":
        order.buyer_id,

        "farmer_id":
        farmer_id,

        "seller_id":
        seller_id,

        "seller_type":
        seller_type,

        "product_id":
        order.product_id,

        "crop":
        product.get("crop"),

        "price_per_unit":
        price_per_unit,

        "image_url":
        product.get("image_url"),

        "quantity":
        quantity,

        "total_amount":
        total_amount,

        "payment_status":
        "pending",

        "payment_method":
        "Mobile Money",

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


    if not order_response.data:

        raise HTTPException(
            status_code=500,
            detail="Failed to create order"
        )


    # ---------------------------------
    # REDUCE PRODUCT STOCK
    # ---------------------------------

    remaining_quantity = (
        float(product["quantity"])
        - quantity
    )


    product_update = {

        "quantity":
        remaining_quantity
    }


    if remaining_quantity <= 0:

        product_update["quantity"] = 0

        product_update["status"] = "sold"


    supabase.table(
        "products"
    ).update(
        product_update
    ).eq(
        "id",
        order.product_id
    ).execute()


    return {

        "message":
        "Order created successfully",

        "order":
        order_response.data[0]
    }


# =====================================
# FARMER ORDERS
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
            "seller_id",
            farmer_id
        )
        .eq(
            "seller_type",
            "farmer"
        )
        .order(
            "created_at",
            desc=True
        )
        .execute()
    )

    return response.data


# =====================================
# SUPPLIER ORDERS
#
# Incoming orders for:
# seeds
# pesticides
# fertilizer
# equipment
# other agricultural inputs
# =====================================

@router.get("/orders/supplier/{supplier_id}")
async def supplier_orders(
    supplier_id: str
):

    response = (
        supabase
        .table("orders")
        .select("*")
        .eq(
            "seller_id",
            supplier_id
        )
        .eq(
            "seller_type",
            "supplier"
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
# GET SINGLE ORDER
# =====================================

@router.get("/orders/{order_id}")
async def get_order_details(
    order_id: str
):

    response = (
        supabase
        .table("orders")
        .select("*")
        .eq(
            "id",
            order_id
        )
        .execute()
    )


    if not response.data:

        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )


    return response.data[0]


# =====================================
# PAY ORDER
# POST /orders/{order_id}/payment
# =====================================

@router.post("/orders/{order_id}/payment")
async def pay_order(
    order_id: str,
    payment: PaymentRequest
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


    if order["payment_status"] == "paid":

        raise HTTPException(
            status_code=400,
            detail="Order already paid"
        )


    supabase.table(
        "orders"
    ).update({

        "payment_status":
        "paid",

        "payment_method":
        payment.payment_method

    }).eq(
        "id",
        order_id
    ).execute()


    return {

        "message":
        "Payment successful",

        "order_id":
        order_id,

        "payment_status":
        "paid",

        "payment_method":
        payment.payment_method
    }


# =====================================
# CANCEL ORDER
# =====================================

@router.put("/orders/{order_id}/cancel")
async def cancel_order(
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


    if order["order_status"] != "placed":

        raise HTTPException(
            status_code=400,
            detail="Order cannot be cancelled"
        )


    supabase.table(
        "orders"
    ).update({

        "order_status":
        "cancelled",

        "status":
        "cancelled"

    }).eq(
        "id",
        order_id
    ).execute()


    return {

        "message":
        "Order cancelled successfully"
    }


# =====================================
# ACCEPT ORDER
# =====================================

@router.put("/orders/{order_id}/accept")
async def accept_order(
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


    if order["order_status"] != "placed":

        raise HTTPException(
            status_code=400,
            detail="Only placed orders can be accepted"
        )


    supabase.table(
        "orders"
    ).update({

        "order_status":
        "accepted",

        "status":
        "accepted",

        "accepted_at":
        datetime.utcnow().isoformat()

    }).eq(
        "id",
        order_id
    ).execute()


    return {

        "message":
        "Order accepted successfully",

        "order_id":
        order_id,

        "order_status":
        "accepted"
    }


# =====================================
# UPDATE ORDER STATUS
#
# Allows seller to move an order
# through the marketplace workflow.
# =====================================

@router.put("/orders/{order_id}/status")
async def update_order_status(
    order_id: str,
    status: str
):

    allowed_statuses = [
        "placed",
        "accepted",
        "processing",
        "ready",
        "completed",
        "cancelled"
    ]


    if status not in allowed_statuses:

        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid order status. "
                f"Allowed: {allowed_statuses}"
            )
        )


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


    supabase.table(
        "orders"
    ).update({

        "order_status":
        status,

        "status":
        status

    }).eq(
        "id",
        order_id
    ).execute()


    return {

        "message":
        "Order status updated successfully",

        "order_id":
        order_id,

        "order_status":
        status
    }


# =====================================
# COMPLETE ORDER
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


    # ---------------------------------
    # PAYMENT CHECK
    # ---------------------------------

    if order["payment_status"] != "paid":

        raise HTTPException(
            status_code=400,
            detail="Buyer has not completed payment."
        )


    # ---------------------------------
    # PREVENT DUPLICATE COMPLETION
    # ---------------------------------

    if order["order_status"] == "completed":

        raise HTTPException(
            status_code=400,
            detail="Order already completed."
        )


    # ---------------------------------
    # UPDATE ORDER
    # ---------------------------------

    supabase.table(
        "orders"
    ).update({

        "status":
        "completed",

        "order_status":
        "completed"

    }).eq(
        "id",
        order_id
    ).execute()


    # =================================
    # FARMER SALE
    # =================================

    if order.get("seller_type") == "farmer":

        farmer_id = (
            order.get("seller_id")
            or order.get("farmer_id")
        )


        if not farmer_id:

            raise HTTPException(
                status_code=400,
                detail="Farmer seller ID is missing"
            )


        # -----------------------------
        # FARMER WALLET
        # -----------------------------

        wallet = (
            supabase
            .table("wallets")
            .select("*")
            .eq(
                "farmer_id",
                farmer_id
            )
            .execute()
        )


        if wallet.data:

            current_balance = (
                wallet.data[0]["balance"]
                or 0
            )


            new_balance = (
                current_balance
                + order["total_amount"]
            )


            supabase.table(
                "wallets"
            ).update({

                "balance":
                new_balance,

                "updated_at":
                datetime.utcnow().isoformat()

            }).eq(
                "farmer_id",
                farmer_id
            ).execute()


        else:

            supabase.table(
                "wallets"
            ).insert({

                "farmer_id":
                farmer_id,

                "balance":
                order["total_amount"],

                "currency":
                "UGX",

                "created_at":
                datetime.utcnow().isoformat()

            }).execute()


        # -----------------------------
        # FARMER TRANSACTION
        # -----------------------------

        supabase.table(
            "transactions"
        ).insert({

            "farmer_id":
            farmer_id,

            "amount":
            order["total_amount"],

            "type":
            "credit",

            "reference_id":
            order_id,

            "description":
            (
                f"{order.get('crop') or 'Marketplace'} "
                "sale"
            ),

            "created_at":
            datetime.utcnow().isoformat()

        }).execute()


        return {

            "message":
            "Order completed and farmer wallet credited.",

            "order_id":
            order_id,

            "seller_type":
            "farmer",

            "amount":
            order["total_amount"]
        }


    # =================================
    # SUPPLIER SALE
    # =================================

    if order.get("seller_type") == "supplier":

        return {

            "message":
            "Supplier order completed successfully.",

            "order_id":
            order_id,

            "seller_id":
            order.get("seller_id"),

            "seller_type":
            "supplier",

            "amount":
            order["total_amount"]
        }


    # =================================
    # UNKNOWN SELLER TYPE
    # =================================

    return {

        "message":
        "Order completed successfully.",

        "order_id":
        order_id,

        "amount":
        order["total_amount"]
    }
