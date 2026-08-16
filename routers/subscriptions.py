from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import supabase

from services.mtn_service import (
    request_payment,
    get_payment_status,
)

from services.subscription_service import (
    get_plan,
    activate_paid_subscription,
)


router = APIRouter()


# ============================================================
# REQUEST MODELS
# ============================================================

class SubscriptionPaymentRequest(BaseModel):

    supplier_id: str
    plan_id: str
    phone_number: str


# ============================================================
# CREATE MTN PAYMENT
#
# POST /api/marketplace/subscriptions/payment
#
# Basic is NOT processed here.
# Basic is activated through the Supabase RPC.
# ============================================================

@router.post("/subscriptions/payment")
async def create_subscription_payment(
    data: SubscriptionPaymentRequest
):

    # ========================================================
    # VALIDATE SUPPLIER
    # ========================================================

    if not data.supplier_id.strip():

        raise HTTPException(
            status_code=400,
            detail="Supplier ID is required."
        )

    if not data.phone_number.strip():

        raise HTTPException(
            status_code=400,
            detail="Mobile Money phone number is required."
        )

    # ========================================================
    # GET PLAN
    # ========================================================

    try:

        plan = get_plan(
            data.plan_id
        )

    except Exception as e:

        raise HTTPException(
            status_code=404,
            detail=str(e)
        )

    plan_name = (
        plan.get("name", "")
        .strip()
        .lower()
    )

    # ========================================================
    # BASIC DOES NOT NEED PAYMENT
    # ========================================================

    if plan_name == "basic":

        raise HTTPException(
            status_code=400,
            detail=(
                "Basic is a free plan and must be "
                "activated through the free subscription flow."
            )
        )

    # ========================================================
    # CHECK PRICE
    # ========================================================

    amount = float(
        plan.get("price_ugx") or 0
    )

    if amount <= 0:

        raise HTTPException(
            status_code=400,
            detail=(
                "This paid plan does not have a valid price."
            )
        )

    # ========================================================
    # CREATE APPLICATION PAYMENT REFERENCE
    # ========================================================

    tx_ref = (
        f"AGRISUB-{uuid.uuid4()}"
    )

    now = datetime.now(
        timezone.utc
    ).isoformat()

    # ========================================================
    # SAVE PAYMENT AS PENDING
    # ========================================================

    payment_response = (
        supabase
        .table("subscription_payments")
        .insert({

            "supplier_id":
                data.supplier_id,

            "plan_id":
                data.plan_id,

            "amount_ugx":
                amount,

            "currency":
                "UGX",

            "payment_provider":
                "mtn",

            "tx_ref":
                tx_ref,

            "payment_method":
                "mobile_money",

            "phone_number":
                data.phone_number,

            "status":
                "pending",

            "created_at":
                now,

            "updated_at":
                now,

        })
        .execute()
    )

    if not payment_response.data:

        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to create subscription payment record."
            )
        )

    payment = (
        payment_response.data[0]
    )

    payment_id = payment["id"]

    # ========================================================
    # SEND PAYMENT REQUEST TO MTN
    # ========================================================

    try:

        mtn = request_payment(

            amount=amount,

            phone_number=data.phone_number,

            external_id=tx_ref,

            payer_message=(
                f"Agri Market {plan.get('name')} subscription"
            ),

            payee_note=(
                "Agri Market subscription payment"
            ),

        )

    except Exception as e:

        supabase \
            .table("subscription_payments") \
            .update({

                "status":
                    "failed",

                "raw_response":
                    {
                        "error": str(e)
                    },

                "updated_at":
                    datetime.now(
                        timezone.utc
                    ).isoformat(),

            }) \
            .eq(
                "id",
                payment_id
            ) \
            .execute()

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    # ========================================================
    # SAVE MTN REFERENCE
    # ========================================================

    mtn_reference = (
        mtn.get("reference_id")
    )

    mtn_status_code = (
        mtn.get("status_code")
    )

    mtn_accepted = (
        mtn.get("accepted") is True
    )

    supabase \
        .table("subscription_payments") \
        .update({

            "provider_reference":
                mtn_reference,

            "raw_response":
                {
                    "status_code":
                        mtn_status_code,

                    "accepted":
                        mtn_accepted,

                    "response":
                        mtn.get("response_text"),

                },

            "updated_at":
                datetime.now(
                    timezone.utc
                ).isoformat(),

        }) \
        .eq(
            "id",
            payment_id
        ) \
        .execute()

    # ========================================================
    # MTN DID NOT ACCEPT REQUEST
    # ========================================================

    if not mtn_accepted:

        supabase \
            .table("subscription_payments") \
            .update({

                "status":
                    "failed",

                "updated_at":
                    datetime.now(
                        timezone.utc
                    ).isoformat(),

            }) \
            .eq(
                "id",
                payment_id
            ) \
            .execute()

        raise HTTPException(

            status_code=400,

            detail=(
                "MTN did not accept the payment request. "
                f"MTN response: "
                f"{mtn.get('response_text')}"
            )

        )

    # ========================================================
    # IMPORTANT
    #
    # DO NOT ACTIVATE SUBSCRIPTION HERE.
    #
    # MTN accepted the REQUEST, but the customer may not
    # have approved the Mobile Money prompt yet.
    # ========================================================

    return {

        "success":
            True,

        "message":
            "Mobile Money payment request sent. "
            "Approve the payment on your phone.",

        "payment_id":
            payment_id,

        "tx_ref":
            tx_ref,

        "provider_reference":
            mtn_reference,

        "status":
            "pending",

        "plan":
            plan.get("name"),

        "amount":
            amount,

    }


# ============================================================
# VERIFY SUBSCRIPTION PAYMENT
#
# GET
# /api/marketplace/subscriptions/payment/{payment_id}/verify
#
# ONLY SUCCESSFUL MTN PAYMENT activates subscription.
# ============================================================

@router.get(
    "/subscriptions/payment/{payment_id}/verify"
)
async def verify_subscription_payment(
    payment_id: str
):

    # ========================================================
    # GET PAYMENT
    # ========================================================

    payment_response = (
        supabase
        .table("subscription_payments")
        .select("*")
        .eq(
            "id",
            payment_id
        )
        .maybe_single()
        .execute()
    )

    if not payment_response.data:

        raise HTTPException(
            status_code=404,
            detail="Subscription payment not found."
        )

    payment = (
        payment_response.data
    )

    # ========================================================
    # ALREADY PAID
    # ========================================================

    if (
        payment.get("status")
        == "paid"
        and payment.get("subscription_id")
    ):

        subscription_response = (
            supabase
            .table("subscriptions")
            .select("*")
            .eq(
                "id",
                payment["subscription_id"]
            )
            .maybe_single()
            .execute()
        )

        return {

            "success":
                True,

            "status":
                "paid",

            "payment":
                payment,

            "subscription":
                subscription_response.data,

        }

    # ========================================================
    # GET MTN REFERENCE
    # ========================================================

    provider_reference = (
        payment.get("provider_reference")
    )

    if not provider_reference:

        raise HTTPException(
            status_code=400,
            detail=(
                "MTN payment reference is not available."
            )
        )

    # ========================================================
    # ASK MTN FOR CURRENT STATUS
    # ========================================================

    try:

        mtn_status = get_payment_status(
            provider_reference
        )

    except Exception as e:

        raise HTTPException(
            status_code=502,
            detail=str(e)
        )

    mtn_status_name = (
        mtn_status
        .get("status", "")
        .strip()
        .upper()
    )

    # ========================================================
    # PAYMENT SUCCESSFUL
    # ========================================================

    if mtn_status_name == "SUCCESSFUL":

        now = datetime.now(
            timezone.utc
        )

        # ----------------------------------------------------
        # Mark payment paid
        # ----------------------------------------------------

        supabase \
            .table("subscription_payments") \
            .update({

                "status":
                    "paid",

                "provider_transaction_id":
                    mtn_status.get(
                        "financialTransactionId"
                    ),

                "paid_at":
                    now.isoformat(),

                "raw_response":
                    mtn_status,

                "updated_at":
                    now.isoformat(),

            }) \
            .eq(
                "id",
                payment_id
            ) \
            .execute()

        # ----------------------------------------------------
        # Activate subscription
        # ----------------------------------------------------

        try:

            subscription = (
                activate_paid_subscription(

                    supplier_id=
                        payment["supplier_id"],

                    plan_id=
                        payment["plan_id"],

                    payment_id=
                        payment_id,

                )
            )

        except Exception as e:

            raise HTTPException(

                status_code=500,

                detail=(
                    "MTN payment was successful, "
                    "but subscription activation failed: "
                    f"{str(e)}"
                )

            )

        return {

            "success":
                True,

            "status":
                "active",

            "message":
                "Payment confirmed and subscription activated.",

            "payment":
                payment,

            "subscription":
                subscription,

        }

    # ========================================================
    # FAILED
    # ========================================================

    if mtn_status_name in [
        "FAILED",
        "REJECTED",
        "CANCELLED",
        "EXPIRED",
    ]:

        supabase \
            .table("subscription_payments") \
            .update({

                "status":
                    "failed",

                "raw_response":
                    mtn_status,

                "updated_at":
                    datetime.now(
                        timezone.utc
                    ).isoformat(),

            }) \
            .eq(
                "id",
                payment_id
            ) \
            .execute()

        return {

            "success":
                False,

            "status":
                "failed",

            "message":
                "Mobile Money payment was not successful.",

            "payment":
                payment,

        }

    # ========================================================
    # STILL WAITING
    # ========================================================

    return {

        "success":
            False,

        "status":
            "pending",

        "message":
            "Payment is still awaiting MTN confirmation.",

        "payment":
            payment,

        "mtn_status":
            mtn_status,

    }


# ============================================================
# GET CURRENT SUPPLIER SUBSCRIPTION
#
# GET /api/marketplace/subscriptions/status/{supplier_id}
# ============================================================

@router.get(
    "/subscriptions/status/{supplier_id}"
)
async def get_subscription_status(
    supplier_id: str
):

    response = (
        supabase
        .table("subscriptions")
        .select(
            """
            *,
            subscription_plans (
                id,
                name,
                description,
                price_ugx,
                billing_interval,
                features
            )
            """
        )
        .eq(
            "supplier_id",
            supplier_id
        )
        .maybe_single()
        .execute()
    )

    if not response.data:

        return {

            "status":
                "none",

            "subscription":
                None,

        }

    subscription = (
        response.data
    )

    # ========================================================
    # CHECK EXPIRY
    # ========================================================

    if (
        subscription.get("status")
        == "active"
        and subscription.get(
            "current_period_end"
        )
    ):

        try:

            expiry = datetime.fromisoformat(
                subscription[
                    "current_period_end"
                ].replace(
                    "Z",
                    "+00:00"
                )
            )

            if expiry < datetime.now(
                timezone.utc
            ):

                supabase \
                    .table("subscriptions") \
                    .update({

                        "status":
                            "expired",

                        "updated_at":
                            datetime.now(
                                timezone.utc
                            ).isoformat(),

                    }) \
                    .eq(
                        "id",
                        subscription["id"]
                    ) \
                    .execute()

                subscription["status"] = (
                    "expired"
                )

        except Exception:
            pass

    return {

        "status":
            subscription.get("status"),

        "subscription":
            subscription,

    }
