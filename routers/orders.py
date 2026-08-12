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
# RELEASE RESERVED STOCK
# ============================================================
#
# Returns reserved product stock to the marketplace.
#
# This function is designed to be idempotent:
#
# If stock has already been released,
# it will not be released again.
#
# Used when:
#
# - Buyer cancels an unpaid order
# - MTN payment fails
# - Order creation needs stock recovery
#
# ============================================================

async def release_reserved_stock(order):
    """
    Release reserved product stock.

    Returns:
        True  -> stock was released
        False -> nothing needed to be released
    """

    # ========================================================
    # CHECK WHETHER STOCK WAS RESERVED
    # ========================================================

    if not order.get("stock_reserved"):

        return False

    # ========================================================
    # PREVENT DOUBLE RELEASE
    # ========================================================

    if order.get("stock_released"):

        return False

    # ========================================================
    # GET PRODUCT INFORMATION
    # ========================================================

    product_id = order.get("product_id")

    quantity = float(
        order.get("quantity") or 0
    )

    if not product_id or quantity <= 0:

        return False

    # ========================================================
    # GET CURRENT PRODUCT
    # ========================================================

    product_response = (
        supabase
        .table("products")
        .select(
            "id, quantity, status"
        )
        .eq(
            "id",
            product_id
        )
        .execute()
    )

    if not product_response.data:

        raise HTTPException(
            status_code=500,
            detail=(
                "Product no longer exists. "
                "Reserved stock could not be restored."
            ),
        )

    product = product_response.data[0]

    current_quantity = float(
        product.get("quantity") or 0
    )

    restored_quantity = (
        current_quantity +
        quantity
    )

    # ========================================================
    # RESTORE STOCK
    # ========================================================

    product_update = {
        "quantity": restored_quantity,
        "status": "available",
    }

    stock_response = (
        supabase
        .table("products")
        .update(product_update)
        .eq(
            "id",
            product_id
        )
        .execute()
    )

    if not stock_response.data:

        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to restore reserved stock."
            ),
        )

    # ========================================================
    # MARK STOCK AS RELEASED
    # ========================================================

    order_id = order.get("id")

    if not order_id:

        raise HTTPException(
            status_code=500,
            detail=(
                "Order ID is missing. "
                "Stock was restored but release "
                "could not be recorded."
            ),
        )

    order_update = (
        supabase
        .table("orders")
        .update({
            "stock_released": True,
            "stock_reserved": False,
        })
        .eq(
            "id",
            order_id
        )
        .eq(
            "stock_released",
            False
        )
        .execute()
    )

    if not order_update.data:

        raise HTTPException(
            status_code=500,
            detail=(
                "Stock was restored but the "
                "order could not be marked "
                "as released."
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
# - Farmer selling produce
# - Supplier selling farm supplies
#
# IMPORTANT:
#
# Stock is reserved BEFORE the order is created.
#
# The stock update uses:
#
#     .gte("quantity", requested_quantity)
#
# so the database only updates the product if
# enough stock still exists at the time of the update.
#
# ============================================================

@router.post("/orders")
async def create_order(
    order: OrderCreate
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
            order.product_id
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

    seller_type = seller_type.lower()
    product_type = product_type.lower()

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
    # RESERVE STOCK
    # ========================================================
    #
    # IMPORTANT:
    #
    # We reserve stock BEFORE creating the order.
    #
    # The WHERE condition:
    #
    #     quantity >= requested quantity
    #
    # prevents an order from reserving stock when the
    # product quantity has already fallen below the
    # requested amount.
    #
    # ========================================================

    new_quantity = (
        available_quantity -
        quantity
    )

    product_update = {
        "quantity": new_quantity,
    }

    # ========================================================
    # PRODUCT IS NOW OUT OF AVAILABLE STOCK
    # ========================================================

    if new_quantity <= 0:

        product_update["quantity"] = 0
        product_update["status"] = "sold"

    # ========================================================
    # CONDITIONAL STOCK UPDATE
    # ========================================================

    stock_response = (
        supabase
        .table("products")
        .update(product_update)
        .eq(
            "id",
            order.product_id
        )
        .gte(
            "quantity",
            quantity
        )
        .execute()
    )

    # ========================================================
    # STOCK RESERVATION FAILED
    # ========================================================

    if not stock_response.data:

        raise HTTPException(
            status_code=409,
            detail=(
                "Product stock changed before "
                "your order could be reserved. "
                "Please refresh and try again."
            ),
        )

    # ========================================================
    # CREATE ORDER
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
        # INVENTORY TRACKING
        # ====================================================

        "stock_reserved":
            True,

        "stock_released":
            False,

        "created_at":
            datetime.utcnow().isoformat(),
    }

    # ========================================================
    # INSERT ORDER
    # ========================================================

    try:

        order_response = (
            supabase
            .table("orders")
            .insert(new_order)
            .execute()
        )

    except Exception as e:

        print(
            "ORDER INSERT FAILED:",
            str(e)
        )

        # ====================================================
        # RESTORE STOCK
        # ====================================================

        restore_response = (
            supabase
            .table("products")
            .select(
                "quantity"
            )
            .eq(
                "id",
                order.product_id
            )
            .execute()
        )

        if restore_response.data:

            current_quantity = float(
                restore_response.data[0].get(
                    "quantity"
                ) or 0
            )

            restored_quantity = (
                current_quantity +
                quantity
            )

            (
                supabase
                .table("products")
                .update({

                    "quantity":
                        restored_quantity,

                    "status":
                        "available",

                })
                .eq(
                    "id",
                    order.product_id
                )
                .execute()
            )

        raise HTTPException(
            status_code=500,
            detail="Failed to create order",
        )

    # ========================================================
    # ORDER INSERT RETURNED NO DATA
    # ========================================================

    if not order_response.data:

        # ====================================================
        # SAFETY RELEASE
        # ====================================================

        restore_response = (
            supabase
            .table("products")
            .select(
                "quantity"
            )
            .eq(
                "id",
                order.product_id
            )
            .execute()
        )

        if restore_response.data:

            current_quantity = float(
                restore_response.data[0].get(
                    "quantity"
                ) or 0
            )

            restored_quantity = (
                current_quantity +
                quantity
            )

            (
                supabase
                .table("products")
                .update({

                    "quantity":
                        restored_quantity,

                    "status":
                        "available",

                })
                .eq(
                    "id",
                    order.product_id
                )
                .execute()
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
# FARMER ORDERS
# ============================================================
#
# GET /orders/farmer/{farmer_id}
#
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
# ============================================================
#
# GET /orders/supplier/{supplier_id}
#
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
# ============================================================
#
# GET /orders/seller/{seller_id}
#
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
# ============================================================
#
# GET /orders/buyer/{buyer_id}
#
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
# ============================================================
#
# GET /orders/{order_id}
#
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
            detail="Order not found",
        )

    return response.data[0]


# ============================================================
# PAY ORDER
# ============================================================
#
# POST /orders/{order_id}/payment
#
# IMPORTANT:
#
# This endpoint initiates MTN COLLECTIONS.
#
# It does NOT immediately mark the order paid.
#
# MTN RequestToPay is asynchronous.
#
# ============================================================

@router.post("/orders/{order_id}/payment")
async def pay_order(
    order_id: str,
    payment: PaymentRequest
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
            order_id
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
    # CHECK EXISTING PAYMENT
    #
    # If a payment is already pending, don't create another
    # MTN RequestToPay transaction.
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
            ""
        )
        .replace(
            "+",
            ""
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
            str(e)
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
            mtn_response.text
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
        .update(payment_update)
        .eq(
            "id",
            order_id
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
# SUCCESSFUL:
#
#     payment_status = paid
#
# FAILED:
#
#     payment_status = failed
#
# IMPORTANT:
#
# Failed payments release reserved stock.
#
# Successful payments KEEP reserved stock.
#
# ============================================================

@router.get(
    "/orders/{order_id}/payment-status"
)
async def check_payment_status(
    order_id: str
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
            order_id
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
            str(e)
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
    #
    # DO NOT RELEASE STOCK.
    #
    # The stock reservation becomes a committed sale.
    # ========================================================

    if mtn_result == "SUCCESSFUL":

        paid_at = (
            datetime.utcnow()
            .isoformat()
        )

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
                order_id
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
    #
    # RELEASE RESERVED STOCK.
    # ========================================================

    if mtn_result in [
        "FAILED",
        "REJECTED",
    ]:

        # ====================================================
        # RELEASE RESERVED STOCK
        # ====================================================

        await release_reserved_stock(
            order
        )

        # ====================================================
        # MARK PAYMENT FAILED
        #
        # Also cancel the order because the buyer did not
        # complete payment.
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
                order_id
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
                True,

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
# PUT /orders/{order_id}/cancel
#
# ONLY unpaid placed orders can be cancelled.
#
# When cancelled:
#
#     reserved stock -> released
#
# ============================================================

@router.put("/orders/{order_id}/cancel")
async def cancel_order(
    order_id: str
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
            order_id
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
    # PAID ORDERS CANNOT BE CANCELLED HERE
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
            order_id
        )
        .execute()
    )

    if not cancel_response.data:

        raise HTTPException(
            status_code=500,
            detail="Failed to cancel order",
        )

    # ========================================================
    # RESPONSE
    # ========================================================

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
# - Farmer selling produce
# - Supplier selling farm supplies
#
# ============================================================

@router.put("/orders/{order_id}/accept")
async def accept_order(
    order_id: str
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
            order_id
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
    # ONLY PLACED ORDERS CAN BE ACCEPTED
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

    seller_type = seller_type.lower()

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
    # ACCEPT ORDER
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
                datetime.utcnow().isoformat(),

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
# `completed` is deliberately blocked.
#
# Completion must go through:
#
#     /orders/{order_id}/complete
#
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

        "cancelled",
    ]

    status = status.lower()

    # ========================================================
    # VALIDATE STATUS
    # ========================================================

    if status not in allowed_statuses:

        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid order status. "
                f"Allowed: {allowed_statuses}"
            ),
        )

    # ========================================================
    # COMPLETION MUST USE DEDICATED ENDPOINT
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
            order_id
        )
        .execute()
    )

    if not order_response.data:

        raise HTTPException(
            status_code=404,
            detail="Order not found",
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
            order_id
        )
        .execute()
    )

    if not update_response.data:

        raise HTTPException(
            status_code=500,
            detail="Failed to update order status",
        )

    return {

        "message":
            "Order status updated successfully",

        "order_id":
            order_id,

        "order_status":
            status,
    }


# ============================================================
# COMPLETE ORDER
# ============================================================
#
# PUT /orders/{order_id}/complete
#
# Seller gets paid here.
#
# Requirements:
#
# 1. Order exists
# 2. Buyer has paid
# 3. Order is accepted OR ready
# 4. Seller exists
#
# IMPORTANT:
#
# reference_id = order_id
#
# This prevents duplicate wallet credits.
#
# Stock is NOT changed here.
#
# Stock was already reserved when the order was created.
#
# ============================================================

@router.put("/orders/{order_id}/complete")
async def complete_order(
    order_id: str
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
            order_id
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
    # ONLY ACCEPTED OR READY ORDERS
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

    seller_type = seller_type.lower()

    # ========================================================
    # VALIDATE SELLER TYPE
    # ========================================================

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
    #
    # Prevent duplicate wallet credits.
    # ========================================================

    existing_transaction = (
        supabase
        .table("transactions")
        .select("*")
        .eq(
            "reference_id",
            order_id
        )
        .eq(
            "type",
            "credit"
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
                order_id
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
                    datetime.utcnow().isoformat(),

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
                datetime.utcnow().isoformat(),
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
            datetime.utcnow().isoformat(),
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
            order_id
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
    # RESPONSE MESSAGE
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

    # ========================================================
    # RESPONSE
    # ========================================================

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
    }
