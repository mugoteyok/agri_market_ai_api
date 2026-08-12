from fastapi import APIRouter, HTTPException

from database import supabase

from schemas.order import OrderCreate
from schemas.payment import PaymentRequest

from services.mtn_service import (
    request_payment,
    get_payment_status,
)

from datetime import datetime

import uuid


router = APIRouter()


# ============================================================
# HELPERS
# ============================================================

def utc_now():
    """
    Return current UTC timestamp in ISO format.
    """
    return datetime.utcnow().isoformat()


# ============================================================
# RESERVE PRODUCT STOCK
# ============================================================
#
# IMPORTANT:
#
# Stock reservation is handled by a PostgreSQL RPC.
#
# This prevents the classic race condition:
#
# Buyer A reads stock = 1
# Buyer B reads stock = 1
#
# Both try to buy 1.
#
# Without row locking, both could succeed.
#
# The RPC locks the product row and checks the current
# quantity inside PostgreSQL.
#
# ============================================================


async def reserve_product_stock(
    product_id: str,
    quantity: float,
):
    """
    Atomically reserve product stock.

    Returns True when stock was successfully reserved.
    Returns False when insufficient stock exists.
    """

    try:

        response = (
            supabase
            .rpc(
                "reserve_product_stock",
                {
                    "p_product_id": product_id,
                    "p_quantity": quantity,
                },
            )
            .execute()
        )

    except Exception as e:

        print(
            "STOCK RESERVATION ERROR:",
            str(e),
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to reserve product stock."
            ),
        )

    # PostgreSQL function returns boolean.
    result = response.data

    if result is True:
        return True

    # Some Supabase responses may return the boolean
    # wrapped in a list/object depending on function definition.
    if isinstance(result, list) and result:

        first = result[0]

        if first is True:
            return True

        if isinstance(first, dict):

            value = (
                first.get("reserve_product_stock")
                or first.get("reserved")
                or first.get("result")
            )

            if value is True:
                return True

    if isinstance(result, dict):

        value = (
            result.get("reserve_product_stock")
            or result.get("reserved")
            or result.get("result")
        )

        if value is True:
            return True

    return False


# ============================================================
# RELEASE RESERVED STOCK
# ============================================================
#
# This function is intentionally idempotent.
#
# If stock was already released, it will not release it again.
#
# ============================================================


async def release_reserved_stock(
    order,
):
    """
    Return reserved stock to the marketplace.

    This should only be called for an order that has reserved
    stock.

    Returns:
        True  = stock released
        False = nothing needed to be released
    """

    # ========================================================
    # CHECK RESERVATION
    # ========================================================

    if not order.get("stock_reserved"):

        return False

    # ========================================================
    # PREVENT DOUBLE RELEASE
    # ========================================================

    if order.get("stock_released"):

        return False

    product_id = (
        order.get("product_id")
    )

    quantity = float(
        order.get("quantity") or 0
    )

    if not product_id:

        raise HTTPException(
            status_code=500,
            detail=(
                "Order does not contain a product ID. "
                "Reserved stock cannot be released."
            ),
        )

    if quantity <= 0:

        raise HTTPException(
            status_code=500,
            detail=(
                "Order contains an invalid quantity. "
                "Reserved stock cannot be released."
            ),
        )

    # ========================================================
    # ATOMICALLY RELEASE STOCK
    # ========================================================

    try:

        response = (
            supabase
            .rpc(
                "release_product_stock",
                {
                    "p_product_id": product_id,
                    "p_quantity": quantity,
                },
            )
            .execute()
        )

    except Exception as e:

        print(
            "STOCK RELEASE ERROR:",
            str(e),
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to restore reserved product stock."
            ),
        )

    result = response.data

    released = False

    if result is True:

        released = True

    elif isinstance(result, list) and result:

        first = result[0]

        if first is True:

            released = True

        elif isinstance(first, dict):

            value = (
                first.get("release_product_stock")
                or first.get("released")
                or first.get("result")
            )

            if value is True:
                released = True

    elif isinstance(result, dict):

        value = (
            result.get("release_product_stock")
            or result.get("released")
            or result.get("result")
        )

        if value is True:
            released = True

    if not released:

        raise HTTPException(
            status_code=500,
            detail=(
                "Product stock could not be released."
            ),
        )

    # ========================================================
    # MARK RESERVATION AS RELEASED
    # ========================================================

    order_id = order.get("id")

    if not order_id:

        raise HTTPException(
            status_code=500,
            detail=(
                "Order ID is missing after stock release."
            ),
        )

    order_update = (
        supabase
        .table("orders")
        .update({

            "stock_released":
                True,

            "stock_reserved":
                False,

        })
        .eq(
            "id",
            order_id,
        )
        .eq(
            "stock_released",
            False,
        )
        .execute()
    )

    if not order_update.data:

        raise HTTPException(
            status_code=500,
            detail=(
                "Stock was restored but the order "
                "could not be marked as released."
            ),
        )

    return True


# ============================================================
# CREATE ORDER
# ============================================================
#
# POST /api/marketplace/orders
#
# Works for:
#
# Farmer selling produce
# Supplier selling farm supplies
#
# Stock is reserved immediately when the order is created.
#
# ============================================================


@router.post("/orders")
async def create_order(
    order: OrderCreate,
):

    # ========================================================
    # GET PRODUCT
    # ========================================================

    product_response = (
        supabase
        .table("products")
        .select("*")
        .eq(
            "id",
            order.product_id,
        )
        .execute()
    )

    if not product_response.data:

        raise HTTPException(
            status_code=404,
            detail="Product not found",
        )

    product = product_response.data[0]

    # ========================================================
    # CHECK PRODUCT STATUS
    # ========================================================

    if product.get("status") not in [
        "available",
        "active",
    ]:

        raise HTTPException(
            status_code=400,
            detail="Product is no longer available",
        )

    # ========================================================
    # CHECK QUANTITY
    # ========================================================

    if order.quantity <= 0:

        raise HTTPException(
            status_code=400,
            detail="Quantity must be greater than zero",
        )

    quantity = float(
        order.quantity
    )

    available_quantity = float(
        product.get("quantity") or 0
    )

    if quantity > available_quantity:

        raise HTTPException(
            status_code=400,
            detail="Insufficient product quantity",
        )

    # ========================================================
    # DETERMINE SELLER
    # ========================================================

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
            detail="Product does not have a seller",
        )

    seller_type = (
        seller_type
        .lower()
    )

    product_type = (
        product_type
        .lower()
    )

    # ========================================================
    # VALIDATE SELLER TYPE
    # ========================================================

    if seller_type not in [
        "farmer",
        "supplier",
    ]:

        raise HTTPException(
            status_code=400,
            detail="Invalid seller type",
        )

    # ========================================================
    # VALIDATE PRODUCT TYPE
    # ========================================================

    if product_type not in [
        "produce",
        "supply",
    ]:

        raise HTTPException(
            status_code=400,
            detail="Invalid product type",
        )

    # ========================================================
    # PRICE
    # ========================================================

    price_per_unit = float(
        product.get("price_per_unit") or 0
    )

    if price_per_unit <= 0:

        raise HTTPException(
            status_code=400,
            detail="Invalid product price",
        )

    total_amount = (
        quantity *
        price_per_unit
    )

    # ========================================================
    # FARMER COMPATIBILITY
    # ========================================================

    farmer_id = None

    if seller_type == "farmer":

        farmer_id = seller_id

    # ========================================================
    # ATOMIC STOCK RESERVATION
    # ========================================================
    #
    # This MUST happen before creating the order.
    #
    # The database RPC locks the product row and verifies
    # the current stock.
    #
    # ========================================================

    stock_reserved = (
        await reserve_product_stock(
            product_id=order.product_id,
            quantity=quantity,
        )
    )

    if not stock_reserved:

        raise HTTPException(
            status_code=409,
            detail=(
                "Product stock changed before "
                "your order could be reserved. "
                "Please refresh and try again."
            ),
        )

    # ========================================================
    # CREATE ORDER DATA
    # ========================================================

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
            product.get("crop")
            or product.get("product_name"),

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

        # ====================================================
        # STOCK TRACKING
        # ====================================================

        "stock_reserved":
            True,

        "stock_released":
            False,

        "created_at":
            utc_now(),
    }

    # ========================================================
    # CREATE ORDER
    # ========================================================

    try:

        order_response = (
            supabase
            .table("orders")
            .insert(
                new_order
            )
            .execute()
        )

    except Exception as e:

        print(
            "ORDER INSERT FAILED:",
            str(e),
        )

        # ====================================================
        # RELEASE STOCK
        # ====================================================

        try:

            await _release_stock_after_failed_order(
                product_id=order.product_id,
                quantity=quantity,
            )

        except Exception as release_error:

            print(
                "CRITICAL STOCK RELEASE ERROR:",
                str(release_error),
            )

        raise HTTPException(
            status_code=500,
            detail="Failed to create order",
        )

    # ========================================================
    # ORDER INSERT RETURNED NO DATA
    # ========================================================

    if not order_response.data:

        try:

            await _release_stock_after_failed_order(
                product_id=order.product_id,
                quantity=quantity,
            )

        except Exception as release_error:

            print(
                "CRITICAL STOCK RELEASE ERROR:",
                str(release_error),
            )

        raise HTTPException(
            status_code=500,
            detail="Failed to create order",
        )

    created_order = (
        order_response.data[0]
    )

    # ========================================================
    # RESPONSE
    # ========================================================

    return {

        "message":
            "Order created successfully",

        "order":
            created_order,

        "stock_reserved":
            True,
    }


# ============================================================
# INTERNAL STOCK RELEASE
# ============================================================
#
# Used when the order INSERT itself fails.
#
# There is no order record yet, so release_reserved_stock()
# cannot be used.
#
# ============================================================


async def _release_stock_after_failed_order(
    product_id: str,
    quantity: float,
):

    try:

        response = (
            supabase
            .rpc(
                "release_product_stock",
                {
                    "p_product_id":
                        product_id,

                    "p_quantity":
                        quantity,
                },
            )
            .execute()
        )

        if response.data is False:

            raise Exception(
                "Database rejected stock release."
            )

    except Exception as e:

        print(
            "FAILED ORDER STOCK RELEASE:",
            str(e),
        )

        raise


# ============================================================
# FARMER ORDERS
# ============================================================
#
# GET /orders/farmer/{farmer_id}
#
# ============================================================


@router.get("/orders/farmer/{farmer_id}")
async def farmer_orders(
    farmer_id: str,
):

    response = (
        supabase
        .table("orders")
        .select("*")
        .eq(
            "seller_id",
            farmer_id,
        )
        .eq(
            "seller_type",
            "farmer",
        )
        .order(
            "created_at",
            desc=True,
        )
        .execute()
    )

    return response.data


# ============================================================
# SUPPLIER ORDERS
# ============================================================
#
# GET /orders/supplier/{supplier_id}
#
# ============================================================


@router.get("/orders/supplier/{supplier_id}")
async def supplier_orders(
    supplier_id: str,
):

    response = (
        supabase
        .table("orders")
        .select("*")
        .eq(
            "seller_id",
            supplier_id,
        )
        .eq(
            "seller_type",
            "supplier",
        )
        .order(
            "created_at",
            desc=True,
        )
        .execute()
    )

    return response.data


# ============================================================
# GENERIC SELLER ORDERS
# ============================================================
#
# GET /orders/seller/{seller_id}
#
# ============================================================


@router.get("/orders/seller/{seller_id}")
async def seller_orders(
    seller_id: str,
):

    response = (
        supabase
        .table("orders")
        .select("*")
        .eq(
            "seller_id",
            seller_id,
        )
        .order(
            "created_at",
            desc=True,
        )
        .execute()
    )

    return response.data


# ============================================================
# BUYER ORDERS
# ============================================================
#
# GET /orders/buyer/{buyer_id}
#
# ============================================================


@router.get("/orders/buyer/{buyer_id}")
async def buyer_orders(
    buyer_id: str,
):

    response = (
        supabase
        .table("orders")
        .select("*")
        .eq(
            "buyer_id",
            buyer_id,
        )
        .order(
            "created_at",
            desc=True,
        )
        .execute()
    )

    return response.data


# ============================================================
# GET SINGLE ORDER
# ============================================================
#
# GET /orders/{order_id}
#
# ============================================================


@router.get("/orders/{order_id}")
async def get_order_details(
    order_id: str,
):

    response = (
        supabase
        .table("orders")
        .select("*")
        .eq(
            "id",
            order_id,
        )
        .execute()
    )

    if not response.data:

        raise HTTPException(
            status_code=404,
            detail="Order not found",
        )

    return response.data[0]


# ============================================================
# PAY ORDER
# ============================================================
#
# POST /orders/{order_id}/payment
#
# MTN RequestToPay is asynchronous.
#
# This endpoint only initiates the payment.
#
# ============================================================


@router.post("/orders/{order_id}/payment")
async def pay_order(
    order_id: str,
    payment: PaymentRequest,
):

    # ========================================================
    # GET ORDER
    # ========================================================

    order_response = (
        supabase
        .table("orders")
        .select("*")
        .eq(
            "id",
            order_id,
        )
        .execute()
    )

    if not order_response.data:

        raise HTTPException(
            status_code=404,
            detail="Order not found",
        )

    order = order_response.data[0]

    # ========================================================
    # PREVENT DOUBLE PAYMENT
    # ========================================================

    if order.get("payment_status") == "paid":

        raise HTTPException(
            status_code=400,
            detail="Order already paid",
        )

    # ========================================================
    # EXISTING PAYMENT
    # ========================================================

    if order.get("payment_status") == "pending":

        existing_reference = (
            order.get("payment_reference")
        )

        if existing_reference:

            return {

                "message":
                    "Payment request already exists.",

                "order_id":
                    order_id,

                "payment_status":
                    "pending",

                "payment_reference":
                    existing_reference,

                "payment_method":
                    order.get(
                        "payment_method"
                    ),
            }

    # ========================================================
    # ONLY PLACED / ACCEPTED ORDERS CAN BE PAID
    # ========================================================

    if order.get("order_status") not in [
        "placed",
        "accepted",
    ]:

        raise HTTPException(
            status_code=400,
            detail=(
                "Order cannot be paid in "
                "its current state"
            ),
        )

    # ========================================================
    # AMOUNT
    # ========================================================

    amount = float(
        order.get("total_amount") or 0
    )

    if amount <= 0:

        raise HTTPException(
            status_code=400,
            detail="Invalid order amount",
        )

    # ========================================================
    # BUYER PHONE NUMBER
    # ========================================================

    phone_number = getattr(
        payment,
        "mobile_number",
        None,
    )

    if not phone_number:

        raise HTTPException(
            status_code=400,
            detail=(
                "Buyer Mobile Money phone "
                "number is required."
            ),
        )

    # ========================================================
    # NORMALIZE PHONE NUMBER
    # ========================================================

    phone_number = (
        phone_number
        .strip()
        .replace(
            " ",
            "",
        )
        .replace(
            "+",
            "",
        )
    )

    if phone_number.startswith("0"):

        phone_number = (
            "256"
            + phone_number[1:]
        )

    # ========================================================
    # BASIC PHONE VALIDATION
    # ========================================================

    if not phone_number.isdigit():

        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid Mobile Money "
                "phone number."
            ),
        )

    if not phone_number.startswith("256"):

        raise HTTPException(
            status_code=400,
            detail=(
                "Use a valid Uganda Mobile "
                "Money number."
            ),
        )

    if len(phone_number) != 12:

        raise HTTPException(
            status_code=400,
            detail=(
                "Use a valid Uganda Mobile "
                "Money number."
            ),
        )

    # ========================================================
    # CREATE MTN REFERENCE
    # ========================================================

    payment_reference = str(
        uuid.uuid4()
    )

    # ========================================================
    # REQUEST MTN PAYMENT
    # ========================================================

    try:

        mtn_response = request_payment(

            amount=amount,

            phone_number=phone_number,

            external_id=
                payment_reference,

            payer_message=(
                f"Agri AI Assist "
                f"order {order_id}"
            ),

            payee_note=(
                "Marketplace order payment"
            ),
        )

    except Exception as e:

        print(
            "MTN PAYMENT ERROR:",
            str(e),
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "Unable to initiate "
                "Mobile Money payment."
            ),
        )

    # ========================================================
    # MTN REQUEST ACCEPTED
    # ========================================================

    if mtn_response.status_code != 202:

        print(
            "MTN PAYMENT FAILED:",
            mtn_response.text,
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "MTN did not accept "
                "the payment request."
            ),
        )

    # ========================================================
    # SAVE PAYMENT REFERENCE
    # ========================================================

    payment_update = {

        "payment_status":
            "pending",

        "payment_method":
            "Mobile Money",

        "payment_reference":
            payment_reference,
    }

    payment_update_response = (
        supabase
        .table("orders")
        .update(
            payment_update
        )
        .eq(
            "id",
            order_id,
        )
        .execute()
    )

    if not payment_update_response.data:

        raise HTTPException(
            status_code=500,
            detail=(
                "MTN payment request was "
                "accepted, but the order "
                "could not be updated."
            ),
        )

    # ========================================================
    # RESPONSE
    # ========================================================

    return {

        "message":
            (
                "Mobile Money payment "
                "request sent successfully."
            ),

        "order_id":
            order_id,

        "amount":
            amount,

        "payment_status":
            "pending",

        "payment_method":
            "Mobile Money",

        "payment_reference":
            payment_reference,

        "next_step":
            (
                "Buyer must approve the "
                "Mobile Money payment."
            ),
    }


# ============================================================
# CHECK PAYMENT STATUS
# ============================================================
#
# GET /orders/{order_id}/payment-status
#
# SUCCESSFUL -> paid
# FAILED     -> failed + stock released
#
# ============================================================


@router.get(
    "/orders/{order_id}/payment-status"
)
async def check_payment_status(
    order_id: str,
):

    # ========================================================
    # GET ORDER
    # ========================================================

    order_response = (
        supabase
        .table("orders")
        .select("*")
        .eq(
            "id",
            order_id,
        )
        .execute()
    )

    if not order_response.data:

        raise HTTPException(
            status_code=404,
            detail="Order not found",
        )

    order = order_response.data[0]

    # ========================================================
    # ALREADY PAID
    # ========================================================

    if order.get("payment_status") == "paid":

        return {

            "order_id":
                order_id,

            "payment_status":
                "paid",

            "message":
                "Payment already confirmed.",
        }

    # ========================================================
    # GET MTN REFERENCE
    # ========================================================

    payment_reference = (
        order.get("payment_reference")
    )

    if not payment_reference:

        raise HTTPException(
            status_code=400,
            detail=(
                "No Mobile Money payment "
                "has been initiated for "
                "this order."
            ),
        )

    # ========================================================
    # QUERY MTN
    # ========================================================

    try:

        mtn_status = get_payment_status(
            payment_reference
        )

    except Exception as e:

        print(
            "MTN STATUS ERROR:",
            str(e),
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "Unable to check "
                "Mobile Money payment status."
            ),
        )

    # ========================================================
    # READ MTN STATUS
    # ========================================================

    mtn_result = (
        str(
            mtn_status.get("status")
            or ""
        )
        .upper()
    )

    # ========================================================
    # SUCCESSFUL
    # ========================================================
    #
    # IMPORTANT:
    #
    # DO NOT RELEASE STOCK.
    #
    # The buyer has paid.
    # The reserved stock is now committed to this order.
    #
    # ========================================================

    if mtn_result == "SUCCESSFUL":

        paid_at = utc_now()

        update_response = (
            supabase
            .table("orders")
            .update({

                "payment_status":
                    "paid",

                "payment_method":
                    "Mobile Money",

                "paid_at":
                    paid_at,

            })
            .eq(
                "id",
                order_id,
            )
            .execute()
        )

        if not update_response.data:

            raise HTTPException(
                status_code=500,
                detail=(
                    "MTN payment was successful "
                    "but the order could not be "
                    "updated."
                ),
            )

        return {

            "order_id":
                order_id,

            "payment_status":
                "paid",

            "mtn_status":
                mtn_result,

            "stock_released":
                False,

            "message":
                "Payment confirmed successfully.",
        }

    # ========================================================
    # FAILED
    # ========================================================
    #
    # Payment failed.
    #
    # Return reserved stock to marketplace.
    #
    # ========================================================

    if mtn_result in [
        "FAILED",
        "REJECTED",
    ]:

        # ====================================================
        # RELEASE STOCK
        # ====================================================

        stock_released = (
            await release_reserved_stock(
                order
            )
        )

        # ====================================================
        # MARK PAYMENT FAILED
        # ====================================================

        update_response = (
            supabase
            .table("orders")
            .update({

                "payment_status":
                    "failed",

                "order_status":
                    "cancelled",

                "status":
                    "cancelled",

            })
            .eq(
                "id",
                order_id,
            )
            .execute()
        )

        if not update_response.data:

            raise HTTPException(
                status_code=500,
                detail=(
                    "Payment failed at MTN, "
                    "but the order could not "
                    "be updated."
                ),
            )

        return {

            "order_id":
                order_id,

            "payment_status":
                "failed",

            "order_status":
                "cancelled",

            "mtn_status":
                mtn_result,

            "stock_released":
                stock_released,

            "message":
                (
                    "Mobile Money payment failed. "
                    "Reserved stock has been released."
                ),
        }

    # ========================================================
    # STILL PROCESSING
    # ========================================================

    return {

        "order_id":
            order_id,

        "payment_status":
            "pending",

        "mtn_status":
            mtn_result
            or "PENDING",

        "stock_released":
            False,

        "message":
            (
                "Mobile Money payment is "
                "still being processed."
            ),
    }


# ============================================================
# CANCEL ORDER
# ============================================================
#
# Only unpaid placed orders can be cancelled.
#
# Cancellation releases reserved stock.
#
# ============================================================


@router.put(
    "/orders/{order_id}/cancel"
)
async def cancel_order(
    order_id: str,
):

    # ========================================================
    # GET ORDER
    # ========================================================

    order_response = (
        supabase
        .table("orders")
        .select("*")
        .eq(
            "id",
            order_id,
        )
        .execute()
    )

    if not order_response.data:

        raise HTTPException(
            status_code=404,
            detail="Order not found",
        )

    order = order_response.data[0]

    # ========================================================
    # ONLY PLACED ORDERS CAN BE CANCELLED
    # ========================================================

    if order.get("order_status") != "placed":

        raise HTTPException(
            status_code=400,
            detail="Order cannot be cancelled",
        )

    # ========================================================
    # NEVER CANCEL A PAID ORDER HERE
    # ========================================================

    if order.get("payment_status") == "paid":

        raise HTTPException(
            status_code=400,
            detail=(
                "Paid orders cannot be cancelled "
                "through this endpoint."
            ),
        )

    # ========================================================
    # RELEASE RESERVED STOCK
    # ========================================================

    stock_released = (
        await release_reserved_stock(
            order
        )
    )

    # ========================================================
    # CANCEL ORDER
    # ========================================================

    cancel_response = (
        supabase
        .table("orders")
        .update({

            "order_status":
                "cancelled",

            "status":
                "cancelled",

        })
        .eq(
            "id",
            order_id,
        )
        .execute()
    )

    if not cancel_response.data:

        raise HTTPException(
            status_code=500,
            detail=(
                "Stock was released but "
                "the order could not be cancelled."
            ),
        )

    return {

        "message":
            "Order cancelled successfully",

        "order_id":
            order_id,

        "order_status":
            "cancelled",

        "stock_released":
            stock_released,
    }


# ============================================================
# ACCEPT ORDER
# ============================================================
#
# PUT /orders/{order_id}/accept
#
# Used by:
#
# Farmer
# Supplier
#
# ============================================================


@router.put(
    "/orders/{order_id}/accept"
)
async def accept_order(
    order_id: str,
):

    # ========================================================
    # GET ORDER
    # ========================================================

    order_response = (
        supabase
        .table("orders")
        .select("*")
        .eq(
            "id",
            order_id,
        )
        .execute()
    )

    if not order_response.data:

        raise HTTPException(
            status_code=404,
            detail="Order not found",
        )

    order = order_response.data[0]

    # ========================================================
    # ONLY PLACED ORDERS
    # ========================================================

    if order.get("order_status") != "placed":

        raise HTTPException(
            status_code=400,
            detail=(
                "Only placed orders "
                "can be accepted"
            ),
        )

    # ========================================================
    # DETERMINE SELLER
    # ========================================================

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
            detail="Order seller is missing",
        )

    seller_type = (
        seller_type
        .lower()
    )

    if seller_type not in [
        "farmer",
        "supplier",
    ]:

        raise HTTPException(
            status_code=400,
            detail="Invalid seller type",
        )

    # ========================================================
    # ACCEPT
    # ========================================================

    accept_response = (
        supabase
        .table("orders")
        .update({

            "order_status":
                "accepted",

            "status":
                "accepted",

            "accepted_at":
                utc_now(),

        })
        .eq(
            "id",
            order_id,
        )
        .execute()
    )

    if not accept_response.data:

        raise HTTPException(
            status_code=500,
            detail="Failed to accept order",
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
            "accepted",
    }


# ============================================================
# UPDATE ORDER STATUS
# ============================================================
#
# PUT /orders/{order_id}/status
#
# Completion MUST go through /complete.
#
# ============================================================


@router.put(
    "/orders/{order_id}/status"
)
async def update_order_status(
    order_id: str,
    status: str,
):

    allowed_statuses = [

        "placed",

        "accepted",

        "processing",

        "ready",

        "completed",

        "cancelled",
    ]

    status = (
        status
        .lower()
    )

    if status not in allowed_statuses:

        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid order status. "
                f"Allowed: {allowed_statuses}"
            ),
        )

    # ========================================================
    # COMPLETION HAS ITS OWN ENDPOINT
    # ========================================================

    if status == "completed":

        raise HTTPException(
            status_code=400,
            detail=(
                "Use the complete order "
                "endpoint to complete "
                "an order."
            ),
        )

    # ========================================================
    # GET ORDER
    # ========================================================

    order_response = (
        supabase
        .table("orders")
        .select("*")
        .eq(
            "id",
            order_id,
        )
        .execute()
    )

    if not order_response.data:

        raise HTTPException(
            status_code=404,
            detail="Order not found",
        )

    order = order_response.data[0]

    # ========================================================
    # CANCELLATION
    # ========================================================
    #
    # If an existing screen uses:
    #
    # PUT /orders/{id}/status?status=cancelled
    #
    # release stock here too.
    #
    # ========================================================

    if status == "cancelled":

        if order.get("payment_status") == "paid":

            raise HTTPException(
                status_code=400,
                detail=(
                    "Paid orders cannot be "
                    "cancelled this way."
                ),
            )

        if order.get("order_status") != "placed":

            raise HTTPException(
                status_code=400,
                detail=(
                    "Only placed orders "
                    "can be cancelled."
                ),
            )

        await release_reserved_stock(
            order
        )

    # ========================================================
    # UPDATE STATUS
    # ========================================================

    update_response = (
        supabase
        .table("orders")
        .update({

            "order_status":
                status,

            "status":
                status,

        })
        .eq(
            "id",
            order_id,
        )
        .execute()
    )

    if not update_response.data:

        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to update order status"
            ),
        )

    return {

        "message":
            "Order status updated successfully",

        "order_id":
            order_id,

        "order_status":
            status,

        "stock_released":
            status == "cancelled",
    }


# ============================================================
# COMPLETE ORDER
# ============================================================
#
# PUT /orders/{order_id}/complete
#
# Requirements:
#
# 1. Order exists
# 2. Buyer has paid
# 3. Order is accepted OR ready
# 4. Seller exists
#
# Seller gets paid here.
#
# reference_id = order_id
#
# Prevents duplicate wallet credits.
#
# ============================================================


@router.put(
    "/orders/{order_id}/complete"
)
async def complete_order(
    order_id: str,
):

    # ========================================================
    # GET ORDER
    # ========================================================

    order_response = (
        supabase
        .table("orders")
        .select("*")
        .eq(
            "id",
            order_id,
        )
        .execute()
    )

    if not order_response.data:

        raise HTTPException(
            status_code=404,
            detail="Order not found",
        )

    order = order_response.data[0]

    # ========================================================
    # PAYMENT CHECK
    # ========================================================

    if order.get("payment_status") != "paid":

        raise HTTPException(
            status_code=400,
            detail=(
                "Buyer has not completed payment."
            ),
        )

    # ========================================================
    # PREVENT DUPLICATE COMPLETION
    # ========================================================

    if order.get("order_status") == "completed":

        raise HTTPException(
            status_code=400,
            detail="Order already completed.",
        )

    # ========================================================
    # ONLY ACCEPTED OR READY
    # ========================================================

    if order.get("order_status") not in [
        "accepted",
        "ready",
    ]:

        raise HTTPException(
            status_code=400,
            detail=(
                "Only accepted or ready orders "
                "can be completed."
            ),
        )

    # ========================================================
    # DETERMINE SELLER
    # ========================================================

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
            detail="Seller ID is missing.",
        )

    seller_type = (
        seller_type
        .lower()
    )

    if seller_type not in [
        "farmer",
        "supplier",
    ]:

        raise HTTPException(
            status_code=400,
            detail="Invalid seller type.",
        )

    # ========================================================
    # AMOUNT
    # ========================================================

    amount = float(
        order.get("total_amount") or 0
    )

    if amount <= 0:

        raise HTTPException(
            status_code=400,
            detail="Invalid order amount.",
        )

    # ========================================================
    # CHECK EXISTING TRANSACTION
    # ========================================================

    existing_transaction = (
        supabase
        .table("transactions")
        .select("*")
        .eq(
            "reference_id",
            order_id,
        )
        .eq(
            "type",
            "credit",
        )
        .execute()
    )

    if existing_transaction.data:

        existing_order_update = (
            supabase
            .table("orders")
            .update({

                "status":
                    "completed",

                "order_status":
                    "completed",

            })
            .eq(
                "id",
                order_id,
            )
            .execute()
        )

        if not existing_order_update.data:

            raise HTTPException(
                status_code=500,
                detail=(
                    "Seller transaction already "
                    "exists, but order could not "
                    "be marked completed."
                ),
            )

        return {

            "message":
                (
                    "Order was already processed. "
                    "Seller wallet was not "
                    "credited again."
                ),

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
                False,

            "already_processed":
                True,
        }

    # ========================================================
    # FIND SELLER WALLET
    # ========================================================

    wallet_response = (
        supabase
        .table("wallets")
        .select("*")
        .eq(
            "seller_id",
            seller_id,
        )
        .eq(
            "seller_type",
            seller_type,
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
                    utc_now(),

            })
            .eq(
                "id",
                wallet["id"],
            )
            .execute()
        )

        if not wallet_update.data:

            raise HTTPException(
                status_code=500,
                detail=(
                    "Failed to update "
                    "seller wallet."
                ),
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
                utc_now(),
        }

        wallet_insert = (
            supabase
            .table("wallets")
            .insert(
                wallet_data
            )
            .execute()
        )

        if not wallet_insert.data:

            raise HTTPException(
                status_code=500,
                detail=(
                    "Failed to create "
                    "seller wallet."
                ),
            )

    # ========================================================
    # CREATE SELLER TRANSACTION
    # ========================================================

    if seller_type == "supplier":

        description = (
            f"{order.get('crop') or 'Farm supply'} "
            "sale"
        )

    else:

        description = (
            f"{order.get('crop') or 'Produce'} "
            "sale"
        )

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
            description,

        "created_at":
            utc_now(),
    }

    transaction_response = (
        supabase
        .table("transactions")
        .insert(
            transaction_data
        )
        .execute()
    )

    if not transaction_response.data:

        raise HTTPException(
            status_code=500,
            detail=(
                "Seller wallet was credited, "
                "but transaction creation "
                "failed. Manual reconciliation "
                "may be required."
            ),
        )

    # ========================================================
    # MARK ORDER COMPLETED
    #
    # IMPORTANT:
    #
    # We do NOT touch product stock here.
    #
    # Stock was already removed/reserved when the order
    # was created.
    #
    # ========================================================

    order_update = (
        supabase
        .table("orders")
        .update({

            "status":
                "completed",

            "order_status":
                "completed",

        })
        .eq(
            "id",
            order_id,
        )
        .execute()
    )

    if not order_update.data:

        raise HTTPException(
            status_code=500,
            detail=(
                "Seller was credited and "
                "transaction was created, "
                "but order completion "
                "update failed."
            ),
        )

    # ========================================================
    # RESPONSE
    # ========================================================

    if seller_type == "farmer":

        message = (
            "Order completed and "
            "farmer wallet credited."
        )

    else:

        message = (
            "Order completed and "
            "supplier wallet credited."
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
            True,

        "already_processed":
            False,

        "stock_released":
            False,
    }
