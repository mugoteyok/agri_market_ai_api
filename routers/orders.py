from fastapi import APIRouter, HTTPException

from database import supabase

from schemas.order import OrderCreate
from schemas.payment import PaymentRequest

from services.mtn_service import (
    request_payment,
    get_payment_status,
)

from services.notification_service import (
    notify_seller,
    notify_buyer,
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
# CREATE ORDER
#
# POST /api/marketplace/orders
#
# IMPORTANT:
#
# Order creation and stock reservation are now handled
# atomically inside PostgreSQL.
#
# PostgreSQL RPC:
#
# create_order_atomic
#
# This means:
#
#     create order
#          +
#     reserve stock
#
# happen inside one database transaction.
#
# If either operation fails, neither is committed.
# ============================================================

@router.post("/orders")
async def create_order(
    order: OrderCreate,
):

    # ========================================================
    # VALIDATE QUANTITY
    # ========================================================

    if order.quantity <= 0:

        raise HTTPException(
            status_code=400,
            detail="Quantity must be greater than zero",
        )

    # ========================================================
    # ATOMIC ORDER CREATION
    #
    # PostgreSQL handles:
    #
    # - product lookup
    # - product availability
    # - stock validation
    # - stock reservation
    # - seller information
    # - price calculation
    # - order creation
    # ========================================================

    try:

        rpc_response = (
            supabase
            .rpc(
                "create_order_atomic",
                {
                    "p_buyer_id":
                        order.buyer_id,

                    "p_product_id":
                        order.product_id,

                    "p_quantity":
                        order.quantity,
                },
            )
            .execute()
        )

    except Exception as e:

        print(
            "CREATE ORDER RPC ERROR:",
            str(e),
        )

        error_message = str(e)

        # ====================================================
        # INSUFFICIENT STOCK
        # ====================================================

        if (
            "Insufficient product quantity"
            in error_message
        ):

            raise HTTPException(
                status_code=409,
                detail=(
                    "Insufficient product quantity"
                ),
            )

        # ====================================================
        # PRODUCT UNAVAILABLE
        # ====================================================

        if (
            "Product is no longer available"
            in error_message
        ):

            raise HTTPException(
                status_code=409,
                detail=(
                    "Product is no longer available"
                ),
            )

        # ====================================================
        # GENERAL FAILURE
        # ====================================================

        raise HTTPException(
            status_code=500,
            detail="Failed to create order",
        )

    # ========================================================
    # RPC RETURNED NO DATA
    # ========================================================

    if not rpc_response.data:

        raise HTTPException(
            status_code=500,
            detail="Failed to create order",
        )

    # ========================================================
    # EXTRACT CREATED ORDER
    # ========================================================

    rpc_data = rpc_response.data

    if isinstance(rpc_data, list):

        rpc_data = rpc_data[0]

    created_order = (
        rpc_data.get("order")
        if isinstance(rpc_data, dict)
        else None
    )

    if not created_order:

        raise HTTPException(
            status_code=500,
            detail="Order was created but could not be read",
        )

    # ========================================================
    # NEW ORDER NOTIFICATION
    # ========================================================

    try:

        buyer_id = created_order.get(
            "buyer_id"
        )

        seller_id = created_order.get(
            "seller_id"
        )

        product_id = created_order.get(
            "product_id"
        )

        product_name = (
            created_order.get("crop")
            or "Marketplace product"
        )

        quantity = created_order.get(
            "quantity"
        )

        total_amount = created_order.get(
            "total_amount"
        )

        # ----------------------------------------------------
        # SELLER NOTIFICATION
        # ----------------------------------------------------

        if seller_id:

            notify_seller(

                seller_id=seller_id,

                notification_type="order",

                title="New order received",

                message=(
                    f"You received a new order for "
                    f"{product_name}."
                ),

                data={

                    "event":
                        "order_created",

                    "order_id":
                        created_order.get("id"),

                    "buyer_id":
                        buyer_id,

                    "seller_id":
                        seller_id,

                    "product_id":
                        product_id,

                    "product_name":
                        product_name,

                    "quantity":
                        quantity,

                    "total_amount":
                        total_amount,

                    "order_status":
                        created_order.get(
                            "order_status"
                        ),

                    "payment_status":
                        created_order.get(
                            "payment_status"
                        ),

                },

            )

    except Exception as e:

        print(
            "ORDER CREATION NOTIFICATION ERROR:",
            str(e),
        )

    # ========================================================
    # RETURN DATABASE RESULT
    # ========================================================

    return rpc_response.data


# ============================================================
# FARMER ORDERS
#
# GET /api/marketplace/orders/farmer/{farmer_id}
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
#
# GET /api/marketplace/orders/supplier/{supplier_id}
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
        .eq(
            "product_type",
            "supply",
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
#
# GET /api/marketplace/orders/seller/{seller_id}
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
#
# GET /api/marketplace/orders/buyer/{buyer_id}
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
#
# GET /api/marketplace/orders/{order_id}
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
# ACCEPT ORDER
#
# PUT /api/marketplace/orders/{order_id}/accept
# ============================================================

@router.put("/orders/{order_id}/accept")
async def accept_order(
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

    order = response.data[0]

    # ========================================================
    # PREVENT ACCEPTING INVALID ORDER STATES
    # ========================================================

    if order.get("order_status") in [
        "completed",
        "cancelled",
    ]:

        raise HTTPException(
            status_code=400,
            detail=(
                "Order cannot be accepted "
                "in its current state."
            ),
        )

    # ========================================================
    # UPDATE ORDER
    # ========================================================

    update_response = (
        supabase
        .table("orders")
        .update({

            "order_status":
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

    if not update_response.data:

        raise HTTPException(
            status_code=500,
            detail="Failed to accept order",
        )

    updated_order = update_response.data[0]

    # ========================================================
    # NOTIFY BUYER
    # ========================================================

    try:

        buyer_id = order.get(
            "buyer_id"
        )

        if buyer_id:

            notify_buyer(

                buyer_id=buyer_id,

                notification_type="order_status",

                title="Order accepted",

                message=(
                    f"Your order for "
                    f"{order.get('crop') or 'your product'} "
                    f"has been accepted by the seller."
                ),

                data={

                    "event":
                        "order_accepted",

                    "order_id":
                        order["id"],

                    "product_id":
                        order.get(
                            "product_id"
                        ),

                    "order_status":
                        "accepted",

                    "seller_id":
                        order.get(
                            "seller_id"
                        ),

                },

            )

    except Exception as e:

        print(
            "ORDER ACCEPT NOTIFICATION ERROR:",
            str(e),
        )

    return updated_order


# ============================================================
# UPDATE ORDER STATUS
#
# PUT /api/marketplace/orders/{order_id}/status?status=processing
#
# Used by supplier/farmer dashboards to move an order through
# its processing lifecycle.
#
# IMPORTANT:
#
# A supplier can only start processing an order after payment
# has been confirmed.
#
# Supported statuses:
#
#     placed
#     accepted
#     processing
#     completed
#     cancelled
#
# IMPORTANT:
#
# We intentionally only update:
#
#     order_status
#     status
#
# here.
#
# This avoids depending on processing_at/completed_at columns
# that may not currently exist in the orders table.
# ============================================================

@router.put("/orders/{order_id}/status")
async def update_order_status(
    order_id: str,
    status: str,
):

    # ========================================================
    # NORMALIZE STATUS
    # ========================================================

    new_status = (
        status
        .strip()
        .lower()
    )

    allowed_statuses = [
        "placed",
        "accepted",
        "processing",
        "completed",
        "cancelled",
    ]

    if new_status not in allowed_statuses:

        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid order status '{status}'. "
                f"Allowed statuses are: "
                f"{', '.join(allowed_statuses)}"
            ),
        )

    # ========================================================
    # GET ORDER
    # ========================================================

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

    order = response.data[0]

    current_status = (
        order.get("order_status")
        or order.get("status")
        or "placed"
    )

    payment_status = (
        order.get("payment_status")
        or "pending"
    )

    # ========================================================
    # PREVENT CHANGING COMPLETED ORDERS
    # ========================================================

    if current_status == "completed":

        raise HTTPException(
            status_code=400,
            detail=(
                "A completed order cannot "
                "be changed."
            ),
        )

    # ========================================================
    # PREVENT CHANGING CANCELLED ORDERS
    # ========================================================

    if current_status == "cancelled":

        raise HTTPException(
            status_code=400,
            detail=(
                "A cancelled order cannot "
                "be changed."
            ),
        )

    # ========================================================
    # PROCESSING REQUIRES PAYMENT
    #
    # This prevents the supplier from processing an unpaid
    # order.
    # ========================================================

    if new_status == "processing":

        if payment_status != "paid":

            raise HTTPException(
                status_code=400,
                detail=(
                    "Order cannot be moved to "
                    "processing because payment "
                    "has not been confirmed."
                ),
            )

    # ========================================================
    # COMPLETED REQUIRES PAYMENT
    # ========================================================

    if new_status == "completed":

        if payment_status != "paid":

            raise HTTPException(
                status_code=400,
                detail=(
                    "A completed order must "
                    "have confirmed payment."
                ),
            )

    # ========================================================
    # BUILD UPDATE
    #
    # IMPORTANT:
    #
    # Only use columns that already exist in the current
    # orders table.
    # ========================================================

    update_data = {

        "order_status":
            new_status,

        "status":
            new_status,

    }

    # ========================================================
    # UPDATE DATABASE
    # ========================================================

    update_response = (
        supabase
        .table("orders")
        .update(update_data)
        .eq(
            "id",
            order_id,
        )
        .execute()
    )

    if not update_response.data:

        raise HTTPException(
            status_code=500,
            detail="Failed to update order",
        )

    updated_order = (
        update_response.data[0]
    )

    # ========================================================
    # NOTIFY BUYER
    # ========================================================

    try:

        buyer_id = order.get(
            "buyer_id"
        )

        product_name = (
            order.get("crop")
            or "your product"
        )

        if buyer_id:

            # ------------------------------------------------
            # PROCESSING
            # ------------------------------------------------

            if new_status == "processing":

                notify_buyer(

                    buyer_id=buyer_id,

                    notification_type="order_status",

                    title="Order processing",

                    message=(
                        f"Your order for "
                        f"{product_name} "
                        f"is now being processed."
                    ),

                    data={

                        "event":
                            "order_processing",

                        "order_id":
                            order_id,

                        "product_id":
                            order.get(
                                "product_id"
                            ),

                        "order_status":
                            new_status,

                        "payment_status":
                            payment_status,

                        "seller_id":
                            order.get(
                                "seller_id"
                            ),

                    },

                )

            # ------------------------------------------------
            # COMPLETED
            # ------------------------------------------------

            elif new_status == "completed":

                notify_buyer(

                    buyer_id=buyer_id,

                    notification_type="order_status",

                    title="Order completed",

                    message=(
                        f"Your order for "
                        f"{product_name} "
                        f"has been completed."
                    ),

                    data={

                        "event":
                            "order_completed",

                        "order_id":
                            order_id,

                        "product_id":
                            order.get(
                                "product_id"
                            ),

                        "order_status":
                            new_status,

                        "payment_status":
                            payment_status,

                        "seller_id":
                            order.get(
                                "seller_id"
                            ),

                    },

                )

    except Exception as e:

        print(
            "ORDER STATUS NOTIFICATION ERROR:",
            str(e),
        )

    # ========================================================
    # RETURN UPDATED ORDER
    # ========================================================

    return updated_order


# ============================================================
# COMPLETE ORDER
#
# PUT /api/marketplace/orders/{order_id}/complete
# ============================================================

@router.put("/orders/{order_id}/complete")
async def complete_order(
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

    order = response.data[0]

    if order.get("order_status") in [
        "completed",
        "cancelled",
    ]:

        raise HTTPException(
            status_code=400,
            detail=(
                "Order cannot be completed "
                "in its current state."
            ),
        )

    update_response = (
        supabase
        .table("orders")
        .update({

            "order_status":
                "completed",

            "status":
                "completed",

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
            detail="Failed to complete order",
        )

    updated_order = update_response.data[0]

    try:

        buyer_id = order.get(
            "buyer_id"
        )

        if buyer_id:

            notify_buyer(

                buyer_id=buyer_id,

                notification_type="order_status",

                title="Order completed",

                message=(
                    f"Your order for "
                    f"{order.get('crop') or 'your product'} "
                    f"has been completed."
                ),

                data={

                    "event":
                        "order_completed",

                    "order_id":
                        order["id"],

                    "product_id":
                        order.get(
                            "product_id"
                        ),

                    "order_status":
                        "completed",

                    "seller_id":
                        order.get(
                            "seller_id"
                        ),

                },

            )

    except Exception as e:

        print(
            "ORDER COMPLETE NOTIFICATION ERROR:",
            str(e),
        )

    return updated_order


# ============================================================
# CANCEL ORDER
#
# PUT /api/marketplace/orders/{order_id}/cancel
# ============================================================

@router.put("/orders/{order_id}/cancel")
async def cancel_order(
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

    order = response.data[0]

    # ========================================================
    # PREVENT CANCELLING COMPLETED ORDER
    # ========================================================

    if order.get("order_status") == "completed":

        raise HTTPException(
            status_code=400,
            detail=(
                "A completed order cannot "
                "be cancelled."
            ),
        )

    # ========================================================
    # ALREADY CANCELLED
    # ========================================================

    if order.get("order_status") == "cancelled":

        return order

    # ========================================================
    # RELEASE RESERVED STOCK
    # ========================================================

    if (
        order.get("stock_reserved")
        and not order.get("stock_released")
    ):

        try:

            release_response = (
                supabase
                .rpc(
                    "release_reserved_stock",
                    {

                        "p_order_id":
                            order_id,

                        "p_payment_status":
                            order.get(
                                "payment_status"
                            ),

                    },
                )
                .execute()
            )

        except Exception as e:

            print(
                "MANUAL CANCEL STOCK RELEASE ERROR:",
                str(e),
            )

            raise HTTPException(
                status_code=500,
                detail=(
                    "Order could not be cancelled "
                    "because reserved stock could "
                    "not be released."
                ),
            )

        if not release_response.data:

            raise HTTPException(
                status_code=500,
                detail=(
                    "Reserved stock could not "
                    "be released."
                ),
            )

        updated_response = (
            supabase
            .table("orders")
            .select("*")
            .eq(
                "id",
                order_id,
            )
            .execute()
        )

        if not updated_response.data:

            raise HTTPException(
                status_code=500,
                detail=(
                    "Order was cancelled but "
                    "could not be retrieved."
                ),
            )

        updated_order = updated_response.data[0]

    else:

        update_response = (
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

        if not update_response.data:

            raise HTTPException(
                status_code=500,
                detail="Failed to cancel order",
            )

        updated_order = update_response.data[0]

    # ========================================================
    # NOTIFY BUYER
    # ========================================================

    try:

        buyer_id = order.get(
            "buyer_id"
        )

        if buyer_id:

            notify_buyer(

                buyer_id=buyer_id,

                notification_type="order_status",

                title="Order cancelled",

                message=(
                    f"Your order for "
                    f"{order.get('crop') or 'your product'} "
                    f"has been cancelled."
                ),

                data={

                    "event":
                        "order_cancelled",

                    "order_id":
                        order["id"],

                    "product_id":
                        order.get(
                            "product_id"
                        ),

                    "order_status":
                        "cancelled",

                    "seller_id":
                        order.get(
                            "seller_id"
                        ),

                },

            )

    except Exception as e:

        print(
            "ORDER CANCEL NOTIFICATION ERROR:",
            str(e),
        )

    return updated_order


# ============================================================
# PAY ORDER
#
# POST /api/marketplace/orders/{order_id}/payment
#
# MTN RequestToPay is asynchronous.
#
# This endpoint ONLY initiates the payment.
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
    # EXISTING PAYMENT REQUEST
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
    # CREATE EXTERNAL PAYMENT ID
    #
    # This is Agri AI Assist's internal transaction ID.
    #
    # It is sent to MTN as externalId.
    #
    # This is NOT the MTN payment reference used for
    # payment status checks.
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
    # READ MTN RESPONSE
    #
    # request_payment() returns a Python dictionary.
    # ========================================================

    print("========== MTN PAYMENT RESPONSE ==========")
    print(mtn_response)
    print("==========================================")

    if not isinstance(mtn_response, dict):

        raise HTTPException(
            status_code=502,
            detail=(
                "Invalid response received "
                "from Mobile Money service."
            ),
        )

    # ========================================================
    # GET STATUS CODE
    # ========================================================

    mtn_status_code = mtn_response.get(
        "status_code"
    )

    # Normalize status code in case MTN service returns
    # "202" instead of 202.
    try:

        mtn_status_code = int(
            mtn_status_code
        )

    except (TypeError, ValueError):

        mtn_status_code = None

    print(
        "MTN STATUS CODE:",
        mtn_status_code,
        type(mtn_status_code),
    )

    # ========================================================
    # MTN REQUEST NOT ACCEPTED
    # ========================================================

    if mtn_status_code != 202:

        error_message = (
            mtn_response.get("message")
            or mtn_response.get("error")
            or mtn_response.get("response")
            or mtn_response.get("detail")
            or mtn_response.get("response_text")
            or "MTN did not accept the payment request."
        )

        print(
            "MTN PAYMENT FAILED:",
            mtn_response,
        )

        raise HTTPException(
            status_code=502,
            detail=str(error_message),
        )

    # ========================================================
    # MTN REQUEST ACCEPTED
    # ========================================================

    print(
        "MTN PAYMENT REQUEST ACCEPTED:",
        mtn_response,
    )

    # ========================================================
    # GET MTN REFERENCE ID
    #
    # This is the X-Reference-Id sent to MTN.
    #
    # It must be stored and later used for payment-status
    # checks.
    # ========================================================

    mtn_reference_id = mtn_response.get(
        "reference_id"
    )

    if not mtn_reference_id:

        raise HTTPException(
            status_code=502,
            detail=(
                "MTN accepted the payment request "
                "but did not return a payment reference."
            ),
        )

    # ========================================================
    # SAVE PAYMENT REFERENCE
    #
    # IMPORTANT:
    #
    # payment_reference:
    #     MTN X-Reference-Id
    #
    # payment_external_id:
    #     Agri AI Assist externalId sent to MTN
    #
    # Both are stored because they serve different purposes.
    # ========================================================

    payment_update = {

        "payment_status":
            "pending",

        "payment_method":
            "Mobile Money",

        # ----------------------------------------------------
        # MTN X-Reference-Id
        #
        # Used for:
        #
        # GET /v1_0/requesttopay/{referenceId}
        #
        # through get_payment_status().
        # ----------------------------------------------------

        "payment_reference":
            mtn_reference_id,

        # ----------------------------------------------------
        # Agri AI Assist externalId
        #
        # Used by the MTN callback/webhook to identify
        # the payment and therefore the order.
        # ----------------------------------------------------

        "payment_external_id":
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

        # MTN X-Reference-Id
        "payment_reference":
            mtn_reference_id,

        # Agri AI Assist externalId
        "payment_external_id":
            payment_reference,

        "next_step":
            (
                "Buyer must approve the "
                "Mobile Money payment."
            ),
    }


# ============================================================
# CHECK PAYMENT STATUS
#
# GET /api/marketplace/orders/{order_id}/payment-status
#
# SUCCESSFUL -> paid
#
# FAILED / REJECTED:
#
#     release reserved stock
#     +
#     cancel order
#
# are handled atomically by PostgreSQL.
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
    #
    # This is the stored MTN X-Reference-Id.
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

        # ====================================================
        # PAYMENT SUCCESS NOTIFICATIONS
        # ====================================================

        try:

            buyer_id = order.get(
                "buyer_id"
            )

            seller_id = order.get(
                "seller_id"
            )

            product_name = (
                order.get("crop")
                or "Marketplace product"
            )

            order_data = {

                "event":
                    "payment_successful",

                "order_id":
                    order_id,

                "product_id":
                    order.get(
                        "product_id"
                    ),

                "product_name":
                    product_name,

                "quantity":
                    order.get(
                        "quantity"
                    ),

                "total_amount":
                    order.get(
                        "total_amount"
                    ),

                "payment_status":
                    "paid",

                "payment_method":
                    "Mobile Money",

                "paid_at":
                    paid_at,

            }

            # ------------------------------------------------
            # BUYER
            # ------------------------------------------------

            if buyer_id:

                notify_buyer(

                    buyer_id=buyer_id,

                    notification_type="payment",

                    title="Payment successful",

                    message=(
                        f"Your payment for "
                        f"{product_name} was successful."
                    ),

                    data=order_data,

                )

            # ------------------------------------------------
            # SELLER
            # ------------------------------------------------

            if seller_id:

                notify_seller(

                    seller_id=seller_id,

                    notification_type="payment",

                    title="Order payment received",

                    message=(
                        f"Payment has been received "
                        f"for your {product_name} order."
                    ),

                    data=order_data,

                )

        except Exception as e:

            print(
                "PAYMENT NOTIFICATION ERROR:",
                str(e),
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

    if mtn_result in [
        "FAILED",
        "REJECTED",
    ]:

        try:

            release_response = (
                supabase
                .rpc(
                    "release_reserved_stock",
                    {
                        "p_order_id":
                            order_id,

                        "p_payment_status":
                            "failed",
                    },
                )
                .execute()
            )

        except Exception as e:

            print(
                "FAILED PAYMENT STOCK RELEASE ERROR:",
                str(e),
            )

            raise HTTPException(
                status_code=500,
                detail=(
                    "Payment failed, but reserved "
                    "stock could not be released."
                ),
            )

        if not release_response.data:

            raise HTTPException(
                status_code=500,
                detail=(
                    "Payment failed, but the order "
                    "could not be released."
                ),
            )

        result = release_response.data

        # ====================================================
        # SAFELY READ RELEASE RESULT
        # ====================================================

        if isinstance(result, dict):

            stock_released = result.get(
                "released",
                False,
            )

        else:

            stock_released = False

        # ====================================================
        # FAILED PAYMENT NOTIFICATIONS
        # ====================================================

        try:

            buyer_id = order.get(
                "buyer_id"
            )

            seller_id = order.get(
                "seller_id"
            )

            product_name = (
                order.get("crop")
                or "Marketplace product"
            )

            notification_data = {

                "event":
                    "payment_failed",

                "order_id":
                    order_id,

                "product_id":
                    order.get(
                        "product_id"
                    ),

                "product_name":
                    product_name,

                "order_status":
                    "cancelled",

                "payment_status":
                    "failed",

                "mtn_status":
                    mtn_result,

                "stock_released":
                    stock_released,

            }

            # ------------------------------------------------
            # BUYER
            # ------------------------------------------------

            if buyer_id:

                notify_buyer(

                    buyer_id=buyer_id,

                    notification_type="payment",

                    title="Payment failed",

                    message=(
                        f"Your payment for "
                        f"{product_name} was not successful. "
                        f"The order has been cancelled."
                    ),

                    data=notification_data,

                )

            # ------------------------------------------------
            # SELLER
            # ------------------------------------------------

            if seller_id:

                notify_seller(

                    seller_id=seller_id,

                    notification_type="order_status",

                    title="Order cancelled",

                    message=(
                        f"The order for {product_name} "
                        f"was cancelled because payment "
                        f"was not successful."
                    ),

                    data=notification_data,

                )

        except Exception as e:

            print(
                "FAILED PAYMENT NOTIFICATION ERROR:",
                str(e),
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
