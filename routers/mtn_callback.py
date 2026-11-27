from datetime import datetime, timezone

from fastapi import APIRouter, Request

from database import get_admin_supabase
from services.mtn_service import (
    get_payment_status,
    verify_collection_payment,
    apply_collection_payment_result,
)
from services.notification_service import (
    notify_buyer,
    notify_seller,
)


router = APIRouter()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def _callback_response(processed: bool, message: str, **extra):
    return {
        "received": True,
        "processed": processed,
        "message": message,
        **extra,
    }


def _notify_success(order: dict, payment_status: dict, paid_at: str):
    buyer_id = order.get("buyer_id")
    seller_id = order.get("seller_id")
    product_name = order.get("crop") or "Marketplace product"

    data = {
        "event": "payment_successful",
        "order_id": order.get("id"),
        "product_id": order.get("product_id"),
        "product_name": product_name,
        "quantity": order.get("quantity"),
        "total_amount": order.get("total_amount"),
        "payment_status": "paid",
        "payment_method": "Mobile Money",
        "paid_at": paid_at,
        "mtn_status": payment_status.get("status"),
        "financial_transaction_id": payment_status.get(
            "financialTransactionId"
        ),
    }

    if buyer_id:
        notify_buyer(
            buyer_id=buyer_id,
            notification_type="payment",
            title="Payment successful",
            message=f"Your payment for {product_name} was successful.",
            data=data,
        )

    if seller_id:
        notify_seller(
            seller_id=seller_id,
            notification_type="payment",
            title="Order payment received",
            message=f"Payment has been received for your {product_name} order.",
            data=data,
        )


def _notify_failure(order: dict, payment_status: dict):
    buyer_id = order.get("buyer_id")
    seller_id = order.get("seller_id")
    product_name = order.get("crop") or "Marketplace product"

    data = {
        "event": "payment_failed",
        "order_id": order.get("id"),
        "product_id": order.get("product_id"),
        "product_name": product_name,
        "order_status": "cancelled",
        "payment_status": "failed",
        "mtn_status": payment_status.get("status"),
        "financial_transaction_id": payment_status.get(
            "financialTransactionId"
        ),
    }

    if buyer_id:
        notify_buyer(
            buyer_id=buyer_id,
            notification_type="payment",
            title="Payment failed",
            message=(
                f"Your payment for {product_name} was not successful. "
                "The order has been cancelled."
            ),
            data=data,
        )

    if seller_id:
        notify_seller(
            seller_id=seller_id,
            notification_type="order_status",
            title="Order cancelled",
            message=(
                f"The order for {product_name} was cancelled because "
                "payment was not successful."
            ),
            data=data,
        )


@router.api_route("/mtn/callback", methods=["POST", "PUT"])
async def mtn_callback(request: Request):
    # Treat the callback as a notification only. Never trust its
    # status/amount/currency as authoritative.
    try:
        payload = await request.json()
    except Exception:
        return _callback_response(False, "Invalid callback JSON.")

    if not isinstance(payload, dict):
        return _callback_response(False, "Invalid callback payload.")

    external_id = str(
        payload.get("externalId")
        or payload.get("externalTransactionId")
        or ""
    ).strip()

    if not external_id:
        return _callback_response(False, "Callback externalId is missing.")

    admin = get_admin_supabase()

    try:
        order_response = (
            admin.table("orders")
            .select("*")
            .eq("payment_external_id", external_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        print("MTN CALLBACK ORDER LOOKUP ERROR:", str(exc))
        return _callback_response(False, "Unable to locate payment order.")

    if not order_response.data:
        return _callback_response(False, "Order not found.")

    order = order_response.data[0]
    order_id = order.get("id")

    current_payment_status = str(
        order.get("payment_status") or ""
    ).strip().lower()

    if current_payment_status == "paid":
        return _callback_response(
            True,
            "Payment already processed.",
            payment_status="paid",
        )

    payment_reference = str(
        order.get("payment_reference") or ""
    ).strip()

    if not payment_reference:
        return _callback_response(
            False,
            "Saved MTN payment reference is missing.",
            reconciliation_required=True,
        )

    # Use the MTN reference saved before initiation to retrieve the
    # authoritative provider status.
    try:
        provider_status = get_payment_status(payment_reference)
    except Exception as exc:
        print("MTN CALLBACK STATUS LOOKUP ERROR:", str(exc))
        return _callback_response(
            False,
            "MTN payment status could not be verified.",
            reconciliation_required=True,
        )

    try:
        verify_collection_payment(order, provider_status)
    except ValueError as exc:
        print("MTN CALLBACK PAYMENT MISMATCH:", str(exc))
        return _callback_response(
            False,
            "MTN payment details do not match this order.",
            reconciliation_required=True,
        )

    authoritative_status = str(
        provider_status.get("status") or ""
    ).strip().upper()

    if authoritative_status == "SUCCESSFUL":
        try:
            transition = apply_collection_payment_result(
                order,
                provider_status,
                admin,
            )
        except Exception as exc:
            print("MTN CALLBACK SUCCESS TRANSITION ERROR:", str(exc))
            return _callback_response(
                False,
                "MTN payment was verified but could not be applied to the order.",
                reconciliation_required=True,
            )

        if not transition.get("processed"):
            return _callback_response(
                False,
                "Verified MTN payment transition was not applied.",
                reconciliation_required=True,
            )

        if not transition.get("newly_paid"):
            return _callback_response(
                True,
                "Payment state was already processed.",
                payment_status=transition.get("payment_status", "paid"),
                reconciliation_required=bool(transition.get("reconciliation_required")),
            )

        paid_at = utc_now()

        try:
            _notify_success(order, provider_status, paid_at)
        except Exception as exc:
            print("MTN CALLBACK SUCCESS NOTIFICATION ERROR:", str(exc))

        return _callback_response(
            True,
            (
                "Payment confirmed; manual reconciliation is required."
                if transition.get("reconciliation_required")
                else "Payment confirmed by MTN."
            ),
            payment_status="paid",
            reconciliation_required=bool(transition.get("reconciliation_required")),
            reconciliation_reason=transition.get("reconciliation_reason"),
        )

    if authoritative_status in {"FAILED", "REJECTED"}:
        try:
            transition = apply_collection_payment_result(
                order,
                provider_status,
                admin,
            )
        except Exception as exc:
            print("MTN CALLBACK FAILURE TRANSITION ERROR:", str(exc))
            return _callback_response(
                False,
                "Verified MTN failure could not be applied to the order.",
                reconciliation_required=True,
            )

        if not transition.get("processed"):
            return _callback_response(
                False,
                "Verified MTN failure transition was not applied.",
                reconciliation_required=True,
            )

        if not transition.get("newly_failed"):
            return _callback_response(
                True,
                "Payment failure was already processed.",
                payment_status=transition.get("payment_status", "failed"),
                stock_released=bool(transition.get("stock_released")),
                already_released=bool(transition.get("already_released")),
            )

        try:
            _notify_failure(order, provider_status)
        except Exception as exc:
            print("MTN CALLBACK FAILURE NOTIFICATION ERROR:", str(exc))

        return _callback_response(
            True,
            "Payment failure confirmed by MTN.",
            payment_status="failed",
            stock_released=bool(transition.get("stock_released")),
            already_released=bool(transition.get("already_released")),
        )

    return _callback_response(
        False,
        "MTN payment is not in a final state.",
        payment_status=authoritative_status or "PENDING",
    )
