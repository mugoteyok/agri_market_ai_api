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
    #
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
    #
    # create_order_atomic returns:
    #
    # {
    #     "message": "...",
    #     "order": {...}
    # }
    #
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
    #
    # Notify the seller that a buyer has placed an order.
    #
    # Notification failure must NOT break order creation.
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
#
# IMPORTANT:
#
# This endpoint is for farmers selling their own produce.
#
# It returns orders where:
#
#     seller_id   = farmer ID
#     seller_type = farmer
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
#
# GET /api/marketplace/orders/supplier/{supplier_id}
#
# IMPORTANT:
#
# This endpoint is ONLY for supplier farm-supply orders.
#
# It will return orders where:
#
#     seller_id    = supplier ID
#     seller_type  = supplier
#     product_type = supply
#
# This prevents supplier dashboards from receiving:
#
#     - farmer produce orders
#     - produce marketplace orders
#     - orders belonging to another seller type
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
#
# IMPORTANT:
#
# DO NOT REMOVE THIS ENDPOINT.
#
# It remains available for the generic seller architecture.
#
# This is useful because a farmer can also sell produce.
#
# Therefore:
#
#     farmer produce
#     supplier supplies
#
# can both use seller_id at the database level.
#
# This endpoint intentionally does NOT filter seller_type
# or product_type.
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
#
# GET /api/marketplace/orders/buyer/{buyer_id}
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
#
# GET /api/marketplace/orders/{order_id}
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
#
# POST /api/marketplace/orders/{order_id}/payment
#
# MTN RequestToPay is asynchronous.
#
# This endpoint ONLY initiates the payment.
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
    # EXISTING PAYMENT REQUEST
    #
    # If MTN payment was already initiated, do not create
    # another payment request.
    #
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
    #
    # IMPORTANT:
    #
    # DO NOT RELEASE STOCK.
    #
    # The buyer has paid.
    # The reserved stock belongs to this order.
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

        # ====================================================
        # PAYMENT SUCCESS NOTIFICATIONS
        #
        # Notify both buyer and seller.
        #
        # Notification failures must NOT affect payment.
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
    #
    # PostgreSQL handles:
    #
    #     release reserved stock
    #            +
    #     cancel order
    #
    # atomically.
    #
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
        #
        # Notify both buyer and seller that the payment failed
        # and the order has been cancelled.
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
