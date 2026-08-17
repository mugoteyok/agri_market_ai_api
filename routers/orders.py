from fastapi import APIRouter, HTTPException

from database import supabase

from schemas.order import OrderCreate
from schemas.payment import PaymentRequest

from services.mtn_service import (
    request_payment,
    get_payment_status,
)

from services.notification_service import (
    create_notification,
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
# NOTIFICATION HELPERS
# ============================================================

def notify_order_created(order):
    """
    Notify the seller when a new order is created.
    """

    seller_id = order.get("seller_id")

    if not seller_id:
        return

    product_type = (
        str(
            order.get("product_type")
            or "produce"
        )
        .lower()
    )

    quantity = order.get("quantity")

    crop = (
        order.get("crop")
        or "product"
    )

    if product_type == "supply":

        title = "New Farm Supply Order"

        message = (
            f"You received a new order for "
            f"{quantity} unit(s) of {crop}."
        )

    else:

        title = "New Produce Order"

        message = (
            f"You received a new order for "
            f"{quantity} unit(s) of {crop}."
        )

    create_notification(
        user_id=str(seller_id),
        title=title,
        message=message,
        notification_type="order",
    )


def notify_payment_success(order):
    """
    Notify both buyer and seller after successful payment.
    """

    buyer_id = order.get("buyer_id")

    seller_id = order.get("seller_id")

    crop = (
        order.get("crop")
        or "your order"
    )

    # --------------------------------------------------------
    # BUYER
    # --------------------------------------------------------

    if buyer_id:

        create_notification(
            user_id=str(buyer_id),
            title="Payment Successful",
            message=(
                f"Your payment for {crop} "
                f"was successfully confirmed."
            ),
            notification_type="order",
        )

    # --------------------------------------------------------
    # SELLER
    # --------------------------------------------------------

    if seller_id:

        create_notification(
            user_id=str(seller_id),
            title="Payment Received",
            message=(
                f"Payment for the {crop} "
                f"order has been successfully confirmed."
            ),
            notification_type="order",
        )


def notify_payment_failed(order):
    """
    Notify buyer when Mobile Money payment fails.
    """

    buyer_id = order.get("buyer_id")

    crop = (
        order.get("crop")
        or "your order"
    )

    if not buyer_id:
        return

    create_notification(
        user_id=str(buyer_id),
        title="Payment Failed",
        message=(
            f"Your Mobile Money payment for "
            f"{crop} failed. The order has been cancelled "
            f"and reserved stock has been released."
        ),
        notification_type="order",
    )


def notify_order_accepted(order):
    """
    Notify buyer when seller accepts the order.
    """

    buyer_id = order.get("buyer_id")

    crop = (
        order.get("crop")
        or "your order"
    )

    if not buyer_id:
        return

    create_notification(
        user_id=str(buyer_id),
        title="Order Accepted",
        message=(
            f"Your order for {crop} "
            f"has been accepted by the seller."
        ),
        notification_type="order",
    )


def notify_order_completed(order):
    """
    Notify buyer when seller completes the order.
    """

    buyer_id = order.get("buyer_id")

    crop = (
        order.get("crop")
        or "your order"
    )

    if not buyer_id:
        return

    create_notification(
        user_id=str(buyer_id),
        title="Order Completed",
        message=(
            f"Your order for {crop} "
            f"has been completed."
        ),
        notification_type="order",
    )


def notify_order_cancelled(
    order,
    cancelled_by: str = "seller",
):
    """
    Notify the relevant party when an order is cancelled.
    """

    buyer_id = order.get("buyer_id")

    seller_id = order.get("seller_id")

    crop = (
        order.get("crop")
        or "your order"
    )

    # --------------------------------------------------------
    # If seller cancelled
    # --------------------------------------------------------

    if cancelled_by == "seller":

        if buyer_id:

            create_notification(
                user_id=str(buyer_id),
                title="Order Cancelled",
                message=(
                    f"Your order for {crop} "
                    f"has been cancelled by the seller."
                ),
                notification_type="order",
            )

    # --------------------------------------------------------
    # If buyer cancelled
    # --------------------------------------------------------

    elif cancelled_by == "buyer":

        if seller_id:

            create_notification(
                user_id=str(seller_id),
                title="Order Cancelled",
                message=(
                    f"The buyer cancelled the "
                    f"{crop} order."
                ),
                notification_type="order",
            )


# ============================================================
# CREATE ORDER
#
# POST /api/marketplace/orders
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
    # GET CREATED ORDER
    # ========================================================

    created_order = (
        rpc_response.data.get(
            "order",
            {}
        )
    )

    # ========================================================
    # NOTIFY SELLER
    #
    # IMPORTANT:
    #
    # Notification failure does NOT affect
    # the successful order.
    # ========================================================

    if created_order:

        notify_order_created(
            created_order
        )

    # ========================================================
    # RETURN DATABASE RESULT
    # ========================================================

    return rpc_response.data


# ============================================================
# FARMER ORDERS
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
            order.get(
                "payment_reference"
            )
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
        order.get(
            "total_amount"
        ) or 0
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
    # NORMALIZE PHONE
    # ========================================================

    phone_number = (
        phone_number
        .strip()
        .replace(" ", "")
        .replace("+", "")
    )

    if phone_number.startswith("0"):

        phone_number = (
            "256"
            + phone_number[1:]
        )

    # ========================================================
    # PHONE VALIDATION
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

            external_id=payment_reference,

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
        order.get(
            "payment_reference"
        )
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

        # ----------------------------------------------------
        # NOTIFICATIONS
        # ----------------------------------------------------

        notify_payment_success(
            order
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

        if isinstance(result, dict):

            stock_released = result.get(
                "released",
                False,
            )

        else:

            stock_released = False

        # ----------------------------------------------------
        # NOTIFY BUYER
        # ----------------------------------------------------

        notify_payment_failed(
            order
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
# ACCEPT ORDER
#
# PUT /api/marketplace/orders/{order_id}/accept
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
    # VALIDATE CURRENT STATUS
    # ========================================================

    if order.get("order_status") != "placed":

        raise HTTPException(
            status_code=400,
            detail=(
                "Only placed orders can be accepted."
            ),
        )

    # ========================================================
    # ACCEPT
    # ========================================================

    update_response = (
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
        .eq(
            "order_status",
            "placed",
        )
        .execute()
    )

    if not update_response.data:

        raise HTTPException(
            status_code=409,
            detail=(
                "Order could not be accepted. "
                "It may have already changed."
            ),
        )

    updated_order = (
        update_response.data[0]
    )

    # ========================================================
    # NOTIFY BUYER
    # ========================================================

    notify_order_accepted(
        updated_order
    )

    return updated_order


# ============================================================
# COMPLETE ORDER
#
# PUT /api/marketplace/orders/{order_id}/complete
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
    # VALIDATE STATUS
    # ========================================================

    if order.get("order_status") != "accepted":

        raise HTTPException(
            status_code=400,
            detail=(
                "Only accepted orders can be completed."
            ),
        )

    # ========================================================
    # COMPLETE
    # ========================================================

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
        .eq(
            "order_status",
            "accepted",
        )
        .execute()
    )

    if not update_response.data:

        raise HTTPException(
            status_code=409,
            detail=(
                "Order could not be completed. "
                "It may have already changed."
            ),
        )

    updated_order = (
        update_response.data[0]
    )

    # ========================================================
    # NOTIFY BUYER
    # ========================================================

    notify_order_completed(
        updated_order
    )

    return updated_order


# ============================================================
# CANCEL ORDER
#
# PUT /api/marketplace/orders/{order_id}/cancel
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
    # PREVENT CANCELLING COMPLETED ORDERS
    # ========================================================

    if order.get("order_status") == "completed":

        raise HTTPException(
            status_code=400,
            detail=(
                "Completed orders cannot be cancelled."
            ),
        )

    # ========================================================
    # ALREADY CANCELLED
    # ========================================================

    if order.get("order_status") == "cancelled":

        return order

    # ========================================================
    # RELEASE RESERVED STOCK
    #
    # This uses your existing safe/idempotent RPC.
    # ========================================================

    if order.get("stock_reserved") and not order.get(
        "stock_released"
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
                            "cancelled",
                    },
                )
                .execute()
            )

        except Exception as e:

            print(
                "CANCEL ORDER STOCK RELEASE ERROR:",
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
                    "Order could not be cancelled."
                ),
            )

    else:

        # ====================================================
        # NO RESERVED STOCK
        # ====================================================

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
                detail=(
                    "Failed to cancel order."
                ),
            )

    # ========================================================
    # GET FINAL ORDER
    # ========================================================

    final_response = (
        supabase
        .table("orders")
        .select("*")
        .eq(
            "id",
            order_id,
        )
        .execute()
    )

    if not final_response.data:

        raise HTTPException(
            status_code=500,
            detail=(
                "Order was cancelled but "
                "could not be retrieved."
            ),
        )

    final_order = (
        final_response.data[0]
    )

    # ========================================================
    # NOTIFY BUYER
    # ========================================================

    notify_order_cancelled(
        final_order,
        cancelled_by="seller",
    )

    return final_order
