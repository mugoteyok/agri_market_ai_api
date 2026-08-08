from fastapi import APIRouter, HTTPException

from database import supabase

from schemas.order import OrderCreate
from schemas.payment import PaymentRequest

from datetime import datetime


router = APIRouter()


# ============================================================
# CREATE ORDER
#
# POST /api/marketplace/orders
#
# Works for:
#
# Farmer selling produce
# Supplier selling farm supplies
#
# Examples:
#
# Produce:
#   maize
#   coffee
#   beans
#   cassava
#
# Farm supplies:
#   seeds
#   pesticides
#   fertilizer
#   equipment
# ============================================================

@router.post("/orders")
async def create_order(
    order: OrderCreate
):

    # --------------------------------------------------------
    # GET PRODUCT
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # CHECK PRODUCT STATUS
    # --------------------------------------------------------

    if product.get("status") != "available":

        raise HTTPException(
            status_code=400,
            detail="Product is no longer available"
        )


    # --------------------------------------------------------
    # CHECK QUANTITY
    # --------------------------------------------------------

    if order.quantity <= 0:

        raise HTTPException(
            status_code=400,
            detail="Quantity must be greater than zero"
        )


    if order.quantity > float(
        product.get("quantity") or 0
    ):

        raise HTTPException(
            status_code=400,
            detail="Insufficient product quantity"
        )


    # --------------------------------------------------------
    # DETERMINE SELLER
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # VALIDATE SELLER TYPE
    # --------------------------------------------------------

    if seller_type not in [
        "farmer",
        "supplier"
    ]:

        raise HTTPException(
            status_code=400,
            detail="Invalid seller type"
        )


    # --------------------------------------------------------
    # VALIDATE PRODUCT TYPE
    # --------------------------------------------------------

    if product_type not in [
        "produce",
        "supply"
    ]:

        raise HTTPException(
            status_code=400,
            detail="Invalid product type"
        )


    # --------------------------------------------------------
    # PRICE
    # --------------------------------------------------------

    quantity = float(
        order.quantity
    )

    price_per_unit = float(
        product.get("price_per_unit") or 0
    )


    if price_per_unit <= 0:

        raise HTTPException(
            status_code=400,
            detail="Invalid product price"
        )


    total_amount = (
        quantity *
        price_per_unit
    )


    # --------------------------------------------------------
    # FARMER COMPATIBILITY
    #
    # Existing farmer orders use farmer_id.
    #
    # Supplier orders:
    #   farmer_id = NULL
    #   seller_id = supplier ID
    # --------------------------------------------------------

    farmer_id = None

    if seller_type == "farmer":

        farmer_id = seller_id


    # --------------------------------------------------------
    # CREATE ORDER
    # --------------------------------------------------------

    new_order = {

        "buyer_id":
            order.buyer_id,

        "farmer_id":
            farmer_id,

        "seller_id":
            seller_id,

        "seller_type":
            seller_type,

        "product_type":
            product_type,

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


    # --------------------------------------------------------
    # REDUCE PRODUCT STOCK
    # --------------------------------------------------------

    remaining_quantity = (
        float(product.get("quantity") or 0)
        - quantity
    )


    product_update = {

        "quantity":
            remaining_quantity
    }


    if remaining_quantity <= 0:

        product_update["quantity"] = 0

        product_update["status"] = "sold"


    supabase \
        .table("products") \
        .update(product_update) \
        .eq(
            "id",
            order.product_id
        ) \
        .execute()


    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------

    return {

        "message":
            "Order created successfully",

        "order":
            order_response.data[0]
    }


# ============================================================
# FARMER ORDERS
#
# Farmer receives orders for produce.
#
# Kept for backward compatibility.
#
# GET /orders/farmer/{farmer_id}
# ============================================================

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


# ============================================================
# SUPPLIER ORDERS
#
# Supplier receives orders for:
#
# seeds
# pesticides
# fertilizer
# equipment
# other farm inputs
#
# GET /orders/supplier/{supplier_id}
# ============================================================

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


# ============================================================
# GENERIC SELLER ORDERS
#
# Works for BOTH:
#
# farmer
# supplier
#
# GET /orders/seller/{seller_id}
# ============================================================

@router.get("/orders/seller/{seller_id}")
async def seller_orders(
    seller_id: str
):

    response = (
        supabase
        .table("orders")
        .select("*")
        .eq(
            "seller_id",
            seller_id
        )
        .order(
            "created_at",
            desc=True
        )
        .execute()
    )


    return response.data


# ============================================================
# BUYER ORDERS
#
# Used when:
#
# Farmer buys supplies
# Buyer buys produce
#
# GET /orders/buyer/{buyer_id}
# ============================================================

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


# ============================================================
# GET SINGLE ORDER
#
# GET /orders/{order_id}
# ============================================================

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


# ============================================================
# PAY ORDER
#
# POST /orders/{order_id}/payment
# ============================================================

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


    # --------------------------------------------------------
    # PREVENT DOUBLE PAYMENT
    # --------------------------------------------------------

    if order.get("payment_status") == "paid":

        raise HTTPException(
            status_code=400,
            detail="Order already paid"
        )


    # --------------------------------------------------------
    # ONLY PLACED / ACCEPTED ORDERS CAN BE PAID
    # --------------------------------------------------------

    if order.get("order_status") not in [
        "placed",
        "accepted"
    ]:

        raise HTTPException(
            status_code=400,
            detail="Order cannot be paid in its current state"
        )


    # --------------------------------------------------------
    # UPDATE PAYMENT
    # --------------------------------------------------------

    payment_response = (
        supabase
        .table("orders")
        .update({

            "payment_status":
                "paid",

            "payment_method":
                payment.payment_method

        })
        .eq(
            "id",
            order_id
        )
        .execute()
    )


    if not payment_response.data:

        raise HTTPException(
            status_code=500,
            detail="Failed to update payment"
        )


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


# ============================================================
# CANCEL ORDER
#
# Only orders that have not been accepted can be cancelled.
# ============================================================

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


    if order.get("order_status") != "placed":

        raise HTTPException(
            status_code=400,
            detail="Order cannot be cancelled"
        )


    cancel_response = (
        supabase
        .table("orders")
        .update({

            "order_status":
                "cancelled",

            "status":
                "cancelled"

        })
        .eq(
            "id",
            order_id
        )
        .execute()
    )


    if not cancel_response.data:

        raise HTTPException(
            status_code=500,
            detail="Failed to cancel order"
        )


    return {

        "message":
            "Order cancelled successfully",

        "order_id":
            order_id,

        "order_status":
            "cancelled"
    }


# ============================================================
# ACCEPT ORDER
#
# Works for:
#
# Farmer seller
# Supplier seller
#
# GET/PUT /orders/{order_id}/accept
# ============================================================

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


    # --------------------------------------------------------
    # ONLY PLACED ORDERS CAN BE ACCEPTED
    # --------------------------------------------------------

    if order.get("order_status") != "placed":

        raise HTTPException(
            status_code=400,
            detail="Only placed orders can be accepted"
        )


    # --------------------------------------------------------
    # VALIDATE SELLER
    # --------------------------------------------------------

    seller_id = (
        order.get("seller_id")
        or order.get("farmer_id")
    )

    seller_type = (
        order.get("seller_type")
        or "farmer"
    )


    if not seller_id:

        raise HTTPException(
            status_code=400,
            detail="Order seller is missing"
        )


    if seller_type not in [
        "farmer",
        "supplier"
    ]:

        raise HTTPException(
            status_code=400,
            detail="Invalid seller type"
        )


    # --------------------------------------------------------
    # ACCEPT ORDER
    # --------------------------------------------------------

    accept_response = (
        supabase
        .table("orders")
        .update({

            "order_status":
                "accepted",

            "status":
                "accepted",

            "accepted_at":
                datetime.utcnow().isoformat()

        })
        .eq(
            "id",
            order_id
        )
        .execute()
    )


    if not accept_response.data:

        raise HTTPException(
            status_code=500,
            detail="Failed to accept order"
        )


    return {

        "message":
            "Order accepted successfully",

        "order_id":
            order_id,

        "seller_id":
            seller_id,

        "seller_type":
            seller_type,

        "order_status":
            "accepted"
    }


# ============================================================
# UPDATE ORDER STATUS
#
# Generic seller status update.
#
# IMPORTANT:
# completed is NOT allowed here.
#
# Completion must go through:
#
# /orders/{order_id}/complete
#
# because that endpoint handles:
#
# wallet credit
# transaction
# payment verification
# ============================================================

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


    status = status.lower()


    if status not in allowed_statuses:

        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid order status. "
                f"Allowed: {allowed_statuses}"
            )
        )


    # --------------------------------------------------------
    # COMPLETED MUST USE COMPLETE ENDPOINT
    # --------------------------------------------------------

    if status == "completed":

        raise HTTPException(
            status_code=400,
            detail=(
                "Use the complete order endpoint "
                "to complete an order."
            )
        )


    # --------------------------------------------------------
    # GET ORDER
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # UPDATE STATUS
    # --------------------------------------------------------

    update_response = (
        supabase
        .table("orders")
        .update({

            "order_status":
                status,

            "status":
                status

        })
        .eq(
            "id",
            order_id
        )
        .execute()
    )


    if not update_response.data:

        raise HTTPException(
            status_code=500,
            detail="Failed to update order status"
        )


    return {

        "message":
            "Order status updated successfully",

        "order_id":
            order_id,

        "order_status":
            status
    }


# ============================================================
# COMPLETE ORDER
#
# This is where the seller gets paid.
#
# Requirements:
#
# 1. Order exists
# 2. Buyer has paid
# 3. Order is accepted
# 4. Seller exists
#
# Then:
#
# Farmer:
#   farmer wallet credited
#
# Supplier:
#   supplier wallet credited
#
# Both:
#   transaction created
#
# Finally:
#   order marked completed
# ============================================================

@router.put("/orders/{order_id}/complete")
async def complete_order(
    order_id: str
):

    # --------------------------------------------------------
    # GET ORDER
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # PAYMENT CHECK
    # --------------------------------------------------------

    if order.get("payment_status") != "paid":

        raise HTTPException(
            status_code=400,
            detail="Buyer has not completed payment."
        )


    # --------------------------------------------------------
    # PREVENT DUPLICATE COMPLETION
    # --------------------------------------------------------

    if order.get("order_status") == "completed":

        raise HTTPException(
            status_code=400,
            detail="Order already completed."
        )


    # --------------------------------------------------------
    # ONLY ACCEPTED ORDERS CAN BE COMPLETED
    # --------------------------------------------------------

    if order.get("order_status") != "accepted":

        raise HTTPException(
            status_code=400,
            detail="Only accepted orders can be completed."
        )


    # --------------------------------------------------------
    # DETERMINE SELLER
    # --------------------------------------------------------

    seller_id = (
        order.get("seller_id")
        or order.get("farmer_id")
    )


    seller_type = (
        order.get("seller_type")
        or "farmer"
    )


    if not seller_id:

        raise HTTPException(
            status_code=400,
            detail="Seller ID is missing."
        )


    if seller_type not in [
        "farmer",
        "supplier"
    ]:

        raise HTTPException(
            status_code=400,
            detail="Invalid seller type."
        )


    # --------------------------------------------------------
    # AMOUNT
    # --------------------------------------------------------

    amount = float(
        order.get("total_amount") or 0
    )


    if amount <= 0:

        raise HTTPException(
            status_code=400,
            detail="Invalid order amount."
        )


    # ========================================================
    # FIND SELLER WALLET
    #
    # Both farmers and suppliers use:
    #
    # seller_id
    # seller_type
    #
    # farmer_id remains populated for farmers.
    # ========================================================

    wallet_response = (
        supabase
        .table("wallets")
        .select("*")
        .eq(
            "seller_id",
            seller_id
        )
        .eq(
            "seller_type",
            seller_type
        )
        .execute()
    )


    # ========================================================
    # UPDATE EXISTING WALLET
    # ========================================================

    if wallet_response.data:

        wallet = wallet_response.data[0]


        current_balance = float(
            wallet.get("balance") or 0
        )


        new_balance = (
            current_balance +
            amount
        )


        wallet_update = (
            supabase
            .table("wallets")
            .update({

                "balance":
                    new_balance,

                "updated_at":
                    datetime.utcnow().isoformat()

            })
            .eq(
                "id",
                wallet["id"]
            )
            .execute()
        )


        if not wallet_update.data:

            raise HTTPException(
                status_code=500,
                detail="Failed to update seller wallet."
            )


    # ========================================================
    # CREATE NEW WALLET
    # ========================================================

    else:

        wallet_data = {

            "farmer_id":
                seller_id
                if seller_type == "farmer"
                else None,

            "seller_id":
                seller_id,

            "seller_type":
                seller_type,

            "balance":
                amount,

            "currency":
                "UGX",

            "updated_at":
                datetime.utcnow().isoformat()
        }


        wallet_insert = (
            supabase
            .table("wallets")
            .insert(wallet_data)
            .execute()
        )


        if not wallet_insert.data:

            raise HTTPException(
                status_code=500,
                detail="Failed to create seller wallet."
            )


    # ========================================================
    # CREATE TRANSACTION
    # ========================================================

    transaction_data = {

        "farmer_id":
            seller_id
            if seller_type == "farmer"
            else None,

        "seller_id":
            seller_id,

        "seller_type":
            seller_type,

        "amount":
            amount,

        "type":
            "credit",

        "status":
            "completed",

        "reference_id":
            order_id,

        "description":
            (
                f"{order.get('crop') or 'Marketplace'} "
                f"{order.get('product_type') or 'produce'} "
                "sale"
            ),

        "created_at":
            datetime.utcnow().isoformat()
    }


    transaction_response = (
        supabase
        .table("transactions")
        .insert(transaction_data)
        .execute()
    )


    if not transaction_response.data:

        raise HTTPException(
            status_code=500,
            detail="Failed to create seller transaction."
        )


    # ========================================================
    # MARK ORDER COMPLETED
    # ========================================================

    order_update = (
        supabase
        .table("orders")
        .update({

            "status":
                "completed",

            "order_status":
                "completed"

        })
        .eq(
            "id",
            order_id
        )
        .execute()
    )


    if not order_update.data:

        raise HTTPException(
            status_code=500,
            detail=(
                "Seller was credited but "
                "order completion update failed."
            )
        )


    # ========================================================
    # RESPONSE
    # ========================================================

    if seller_type == "farmer":

        message = (
            "Order completed and farmer wallet credited."
        )

    else:

        message = (
            "Order completed and supplier wallet credited."
        )


    return {

        "message":
            message,

        "order_id":
            order_id,

        "seller_id":
            seller_id,

        "seller_type":
            seller_type,

        "product_type":
            order.get("product_type")
            or "produce",

        "amount":
            amount,

        "order_status":
            "completed",

        "wallet_credited":
            True
    }
