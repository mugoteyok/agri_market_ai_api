from fastapi import APIRouter, Request
from database import supabase
from services.notification_service import (
    notify_seller,
    notify_buyer,
)
from datetime import datetime


router = APIRouter()


def utc_now():
    return datetime.utcnow().isoformat()


@router.post("/mtn/callback")
async def mtn_callback(request: Request):

    # ========================================================
    # READ MTN CALLBACK
    # ========================================================

    try:
        payload = await request.json()

    except Exception as e:

        print(
            "MTN CALLBACK JSON ERROR:",
            str(e),
        )

        return {
            "received": False,
            "message": "Invalid callback payload",
        }

    print("========== MTN CALLBACK ==========")
    print("PAYLOAD:", payload)
    print("==================================")

    # ========================================================
    # MTN CALLBACK FIELDS
    #
    # RequestToPay callbacks contain information equivalent
    # to the transaction status response.
    # ========================================================

    mtn_status = str(
        payload.get("status")
        or ""
    ).upper()

    external_id = (
        payload.get("externalId")
        or payload.get("externalTransactionId")
    )

    financial_transaction_id = (
        payload.get("financialTransactionId")
    )

    print(
        "MTN CALLBACK STATUS:",
        mtn_status,
    )

    print(
        "MTN CALLBACK EXTERNAL ID:",
        external_id,
    )

    print(
        "MTN FINANCIAL TRANSACTION ID:",
        financial_transaction_id,
    )

    # ========================================================
    # WE REQUIRE THE EXTERNAL ID
    #
    # In our payment flow, this is Agri AI Assist's internal
    # payment ID.
    #
    # IMPORTANT:
    #
    # We currently generate payment_reference in orders.py
    # and send it to MTN as externalId.
    #
    # Therefore we can use externalId to locate the order.
    # ========================================================

    if not external_id:

        print(
            "MTN CALLBACK ERROR: "
            "externalId missing."
        )

        return {
            "received": True,
            "processed": False,
            "message": "externalId missing",
        }

    # ========================================================
    # FIND ORDER
    #
    # payment_reference currently stores the MTN X-Reference-Id,
    # NOT externalId.
    #
    # Therefore we first try to locate the order using the
    # external ID.
    #
    # This requires storing the external ID separately.
    # ========================================================

    response = (
        supabase
        .table("orders")
        .select("*")
        .eq(
            "payment_external_id",
            external_id,
        )
        .execute()
    )

    if not response.data:

        print(
            "MTN CALLBACK: "
            "No order found for externalId:",
            external_id,
        )

        return {
            "received": True,
            "processed": False,
            "message": "Order not found",
        }

    order = response.data[0]

    order_id = order.get("id")

    print(
        "MTN CALLBACK ORDER:",
        order_id,
    )

    # ========================================================
    # IDEMPOTENCY
    #
    # MTN may only send the callback once, but our endpoint
    # should still be safe if the same request is delivered
    # more than once.
    # ========================================================

    if order.get("payment_status") == "paid":

        return {
            "received": True,
            "processed": True,
            "message": "Payment already processed",
        }

    # ========================================================
    # SUCCESSFUL
    # ========================================================

    if mtn_status == "SUCCESSFUL":

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

            print(
                "MTN CALLBACK ERROR: "
                "Order update failed."
            )

            return {
                "received": True,
                "processed": False,
                "message": "Order update failed",
            }

        # ====================================================
        # NOTIFICATIONS
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

                "mtn_status":
                    mtn_status,

                "financial_transaction_id":
                    financial_transaction_id,

            }

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
                "MTN CALLBACK NOTIFICATION ERROR:",
                str(e),
            )

        return {
            "received": True,
            "processed": True,
            "payment_status": "paid",
        }

    # ========================================================
    # FAILED / REJECTED
    # ========================================================

    if mtn_status in [
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
                "MTN CALLBACK STOCK RELEASE ERROR:",
                str(e),
            )

            return {
                "received": True,
                "processed": False,
                "message":
                    "Payment failed but stock release failed",
            }

        if not release_response.data:

            return {
                "received": True,
                "processed": False,
                "message":
                    "Payment failed but order update failed",
            }

        # ====================================================
        # NOTIFICATIONS
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
                    mtn_status,

                "financial_transaction_id":
                    financial_transaction_id,

            }

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
                "MTN CALLBACK FAILURE NOTIFICATION ERROR:",
                str(e),
            )

        return {
            "received": True,
            "processed": True,
            "payment_status": "failed",
        }

    # ========================================================
    # UNKNOWN / PENDING
    # ========================================================

    return {
        "received": True,
        "processed": False,
        "payment_status":
            mtn_status or "PENDING",
    }
