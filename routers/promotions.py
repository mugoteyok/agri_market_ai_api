
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from database import supabase

from services.mtn_service import (
    request_payment,
    get_payment_status,
)

from datetime import datetime, timezone
import uuid


router = APIRouter()


# ============================================================
# REQUEST MODEL
# ============================================================

class PromotionCreate(BaseModel):

    product_id: str

    seller_id: str

    seller_type: str = "supplier"

    promoted_price: float = Field(gt=0)

    duration_days: int = Field(gt=0)


# ============================================================
# PAYMENT REQUEST MODEL
# ============================================================

class PromotionPaymentRequest(BaseModel):

    mobile_number: str


# ============================================================
# PROMOTION PRICING
# ============================================================

PROMOTION_PRICES = {

    7: 5000,

    14: 8000,

    30: 15000,

}


# ============================================================
# GET PROMOTION FEE
# ============================================================

def get_promotion_fee(
    duration_days: int
) -> float:

    if duration_days not in PROMOTION_PRICES:

        raise HTTPException(

            status_code=400,

            detail=(
                "Invalid promotion duration. "
                "Available durations are "
                "7, 14, or 30 days."
            )

        )

    return float(
        PROMOTION_PRICES[
            duration_days
        ]
    )


# ============================================================
# NORMALIZE PHONE NUMBER
# ============================================================

def normalize_phone_number(
    phone_number: str
) -> str:

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

    if not phone_number.isdigit():

        raise HTTPException(

            status_code=400,

            detail=(
                "Invalid Mobile Money "
                "phone number."
            )

        )

    if not phone_number.startswith("256"):

        raise HTTPException(

            status_code=400,

            detail=(
                "Use a valid Uganda "
                "Mobile Money number."
            )

        )

    return phone_number


# ============================================================
# CREATE PROMOTION
#
# POST /promotions
#
# Promotion starts as PENDING.
#
# Payment is required before activation.
# ============================================================

@router.post("/promotions")
async def create_promotion(
    promotion: PromotionCreate
):

    # ========================================================
    # VALIDATE SELLER TYPE
    # ========================================================

    seller_type = (
        promotion.seller_type
        or "supplier"
    ).lower().strip()

    if seller_type != "supplier":

        raise HTTPException(

            status_code=400,

            detail=(
                "Only suppliers can "
                "promote farm-supply products."
            )

        )


    # ========================================================
    # VALIDATE DURATION
    # ========================================================

    promotion_fee = get_promotion_fee(
        promotion.duration_days
    )


    # ========================================================
    # GET PRODUCT
    # ========================================================

    try:

        product_response = (

            supabase

            .table("products")

            .select("*")

            .eq(
                "id",
                promotion.product_id
            )

            .execute()

        )

    except Exception as e:

        raise HTTPException(

            status_code=500,

            detail=(
                "Could not retrieve product: "
                f"{str(e)}"
            )

        )


    if not product_response.data:

        raise HTTPException(

            status_code=404,

            detail="Product not found."

        )


    product = product_response.data[0]


    # ========================================================
    # VERIFY PRODUCT BELONGS TO SUPPLIER
    # ========================================================

    if (
        product.get("seller_id")
        != promotion.seller_id
    ):

        raise HTTPException(

            status_code=403,

            detail=(
                "This supplier does not "
                "own this product."
            )

        )


    # ========================================================
    # VERIFY SELLER TYPE
    # ========================================================

    if product.get("seller_type") != "supplier":

        raise HTTPException(

            status_code=400,

            detail=(
                "Only supplier products "
                "can be promoted."
            )

        )


    # ========================================================
    # VERIFY PRODUCT TYPE
    # ========================================================

    if product.get("product_type") != "supply":

        raise HTTPException(

            status_code=400,

            detail=(
                "Only farm-supply products "
                "can be promoted."
            )

        )


    # ========================================================
    # VERIFY PRODUCT STATUS
    # ========================================================

    if product.get("status") != "available":

        raise HTTPException(

            status_code=400,

            detail=(
                "Only available products "
                "can be promoted."
            )

        )


    # ========================================================
    # ORIGINAL PRICE
    # ========================================================

    original_price = float(

        product.get(
            "price_per_unit"
        ) or 0

    )


    if original_price <= 0:

        raise HTTPException(

            status_code=400,

            detail=(
                "Product has an invalid price."
            )

        )


    # ========================================================
    # PROMOTED PRICE
    # ========================================================

    promoted_price = float(
        promotion.promoted_price
    )


    if promoted_price >= original_price:

        raise HTTPException(

            status_code=400,

            detail=(
                "Promoted price must be "
                "lower than the original price."
            )

        )


    # ========================================================
    # CALCULATE DISCOUNT
    # ========================================================

    discount_percentage = (

        (
            original_price
            - promoted_price
        )
        / original_price

    ) * 100


    discount_percentage = round(
        discount_percentage,
        2
    )


    # ========================================================
    # CHECK EXISTING PROMOTION
    # ========================================================

    try:

        existing_response = (

            supabase

            .table("product_promotions")

            .select("*")

            .eq(
                "product_id",
                promotion.product_id
            )

            .in_(
                "status",
                [
                    "pending",
                    "active"
                ]
            )

            .execute()

        )

    except Exception as e:

        raise HTTPException(

            status_code=500,

            detail=(
                "Could not check existing "
                f"promotions: {str(e)}"
            )

        )


    if existing_response.data:

        raise HTTPException(

            status_code=400,

            detail=(
                "This product already has "
                "a pending or active promotion."
            )

        )


    # ========================================================
    # PROMOTION DATES
    #
    # IMPORTANT:
    #
    # Do NOT start the promotion clock yet.
    #
    # Payment has not happened.
    #
    # The payment-status endpoint will set
    # starts_at and expires_at after successful payment.
    # ========================================================

    now = datetime.now(
        timezone.utc
    )


    # ========================================================
    # CREATE PROMOTION
    # ========================================================

    promotion_data = {

        "product_id":
            promotion.product_id,

        "seller_id":
            promotion.seller_id,

        "seller_type":
            seller_type,

        "promotion_type":
            "discounted",

        "original_price":
            original_price,

        "promoted_price":
            promoted_price,

        "discount_percentage":
            discount_percentage,

        "duration_days":
            promotion.duration_days,

        # Will be set after successful payment.
        "starts_at":
            now.isoformat(),

        # Temporary value.
        #
        # It will be replaced after payment.
        "expires_at":
            now.isoformat(),

        "payment_status":
            "pending",

        "payment_reference":
            None,

        "payment_method":
            None,

        "paid_at":
            None,

        "status":
            "pending",

        "created_at":
            now.isoformat()

    }


    # ========================================================
    # INSERT
    # ========================================================

    try:

        response = (

            supabase

            .table("product_promotions")

            .insert(
                promotion_data
            )

            .execute()

        )

    except Exception as e:

        raise HTTPException(

            status_code=500,

            detail=(
                "Could not create promotion: "
                f"{str(e)}"
            )

        )


    if not response.data:

        raise HTTPException(

            status_code=500,

            detail=(
                "Promotion could not be created."
            )

        )


    # ========================================================
    # RESPONSE
    # ========================================================

    return {

        "message":
            (
                "Promotion created successfully. "
                "Mobile Money payment is required."
            ),

        "promotion":
            response.data[0],

        "promotion_fee":
            promotion_fee,

        "currency":
            "UGX",

        "payment_status":
            "pending"

    }


# ============================================================
# PAY FOR PROMOTION
#
# POST /promotions/{promotion_id}/payment
#
# Uses the EXISTING MTN COLLECTIONS integration.
# ============================================================

@router.post(
    "/promotions/{promotion_id}/payment"
)
async def pay_for_promotion(
    promotion_id: str,
    payment: PromotionPaymentRequest
):

    # ========================================================
    # GET PROMOTION
    # ========================================================

    response = (

        supabase

        .table("product_promotions")

        .select("*")

        .eq(
            "id",
            promotion_id
        )

        .execute()

    )


    if not response.data:

        raise HTTPException(

            status_code=404,

            detail="Promotion not found."

        )


    promotion = response.data[0]


    # ========================================================
    # PREVENT DOUBLE PAYMENT
    # ========================================================

    if (
        promotion.get("payment_status")
        == "paid"
    ):

        raise HTTPException(

            status_code=400,

            detail=(
                "This promotion has "
                "already been paid for."
            )

        )


    # ========================================================
    # PREVENT CANCELLED / EXPIRED
    # ========================================================

    if promotion.get("status") in [
        "cancelled",
        "expired"
    ]:

        raise HTTPException(

            status_code=400,

            detail=(
                "This promotion can no "
                "longer be paid for."
            )

        )


    # ========================================================
    # PROMOTION FEE
    # ========================================================

    duration_days = int(

        promotion.get(
            "duration_days"
        ) or 0

    )


    promotion_fee = get_promotion_fee(
        duration_days
    )


    # ========================================================
    # EXISTING PAYMENT
    # ========================================================

    existing_reference = (

        promotion.get(
            "payment_reference"
        )

    )


    if (
        promotion.get("payment_status")
        == "pending"
        and existing_reference
    ):

        return {

            "message":
                "Payment request already exists.",

            "promotion_id":
                promotion_id,

            "amount":
                promotion_fee,

            "currency":
                "UGX",

            "payment_status":
                "pending",

            "payment_reference":
                existing_reference,

            "payment_method":
                promotion.get(
                    "payment_method"
                )

        }


    # ========================================================
    # PHONE NUMBER
    # ========================================================

    phone_number = normalize_phone_number(
        payment.mobile_number
    )


    # ========================================================
    # CREATE PAYMENT REFERENCE
    # ========================================================

    payment_reference = str(
        uuid.uuid4()
    )


    # ========================================================
    # REQUEST MTN PAYMENT
    #
    # REUSES EXISTING PAYMENT SYSTEM.
    # ========================================================

    try:

        mtn_response = request_payment(

            amount=promotion_fee,

            phone_number=phone_number,

            external_id=
                payment_reference,

            payer_message=(
                "Agri AI Assist "
                "product promotion"
            ),

            payee_note=(
                "Farm supply "
                "promotion payment"
            )

        )

    except Exception as e:

        print(
            "PROMOTION MTN PAYMENT ERROR:",
            str(e)
        )

        raise HTTPException(

            status_code=502,

            detail=(
                "Unable to initiate "
                "Mobile Money payment."
            )

        )


    # ========================================================
    # MTN REQUEST ACCEPTED
    # ========================================================

    if mtn_response.status_code != 202:

        print(
            "PROMOTION MTN PAYMENT FAILED:",
            mtn_response.text
        )

        raise HTTPException(

            status_code=502,

            detail=(
                "MTN did not accept "
                "the promotion payment request."
            )

        )


    # ========================================================
    # SAVE PAYMENT INFORMATION
    # ========================================================

    payment_update = {

        "payment_status":
            "pending",

        "payment_reference":
            payment_reference,

        "payment_method":
            "Mobile Money"

    }


    payment_update_response = (

        supabase

        .table("product_promotions")

        .update(
            payment_update
        )

        .eq(
            "id",
            promotion_id
        )

        .execute()

    )


    if not payment_update_response.data:

        raise HTTPException(

            status_code=500,

            detail=(
                "MTN payment request was "
                "accepted, but the promotion "
                "could not be updated."
            )

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

        "promotion_id":
            promotion_id,

        "amount":
            promotion_fee,

        "currency":
            "UGX",

        "payment_status":
            "pending",

        "payment_method":
            "Mobile Money",

        "payment_reference":
            payment_reference,

        "next_step":
            (
                "Approve the Mobile Money "
                "payment, then check payment status."
            )

    }


# ============================================================
# CHECK PROMOTION PAYMENT STATUS
#
# GET /promotions/{promotion_id}/payment-status
#
# Successful payment:
#
# payment_status = paid
# status = active
#
# starts_at = payment confirmation time
# expires_at = starts_at + duration
# ============================================================

@router.get(
    "/promotions/{promotion_id}/payment-status"
)
async def check_promotion_payment_status(
    promotion_id: str
):

    # ========================================================
    # GET PROMOTION
    # ========================================================

    response = (

        supabase

        .table("product_promotions")

        .select("*")

        .eq(
            "id",
            promotion_id
        )

        .execute()

    )


    if not response.data:

        raise HTTPException(

            status_code=404,

            detail="Promotion not found."

        )


    promotion = response.data[0]


    # ========================================================
    # ALREADY PAID
    # ========================================================

    if (
        promotion.get("payment_status")
        == "paid"
    ):

        # Check whether it has expired.
        expires_at_value = (
            promotion.get(
                "expires_at"
            )
        )

        if expires_at_value:

            expires_at = datetime.fromisoformat(

                expires_at_value.replace(
                    "Z",
                    "+00:00"
                )

            )

            now = datetime.now(
                timezone.utc
            )

            if expires_at <= now:

                expire_response = (

                    supabase

                    .table(
                        "product_promotions"
                    )

                    .update({

                        "status":
                            "expired"

                    })

                    .eq(
                        "id",
                        promotion_id
                    )

                    .execute()

                )

                if expire_response.data:

                    promotion = (
                        expire_response.data[0]
                    )

        return {

            "promotion_id":
                promotion_id,

            "payment_status":
                promotion.get(
                    "payment_status"
                ),

            "promotion_status":
                promotion.get(
                    "status"
                ),

            "payment_reference":
                promotion.get(
                    "payment_reference"
                ),

            "message":
                (
                    "Promotion payment "
                    "already confirmed."
                )

        }


    # ========================================================
    # PAYMENT REFERENCE
    # ========================================================

    payment_reference = (

        promotion.get(
            "payment_reference"
        )

    )


    if not payment_reference:

        raise HTTPException(

            status_code=400,

            detail=(
                "No Mobile Money payment "
                "has been initiated for "
                "this promotion."
            )

        )


    # ========================================================
    # QUERY MTN
    #
    # REUSES EXISTING PAYMENT SERVICE.
    # ========================================================

    try:

        mtn_status = get_payment_status(
            payment_reference
        )

    except Exception as e:

        print(
            "PROMOTION MTN STATUS ERROR:",
            str(e)
        )

        raise HTTPException(

            status_code=502,

            detail=(
                "Unable to check "
                "Mobile Money payment status."
            )

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
    # SUCCESSFUL PAYMENT
    # ========================================================

    if mtn_result == "SUCCESSFUL":

        paid_at = datetime.now(
            timezone.utc
        )


        # ====================================================
        # CALCULATE PROMOTION DATES
        # ====================================================

        duration_days = int(

            promotion.get(
                "duration_days"
            ) or 0

        )


        if duration_days not in PROMOTION_PRICES:

            raise HTTPException(

                status_code=400,

                detail=(
                    "Invalid promotion "
                    "duration."
                )

            )


        starts_at = paid_at

        expires_at = (

            starts_at
            + __import__(
                "datetime"
            ).timedelta(
                days=duration_days
            )

        )


        # ====================================================
        # ACTIVATE PROMOTION
        # ====================================================

        update_response = (

            supabase

            .table(
                "product_promotions"
            )

            .update({

                "payment_status":
                    "paid",

                "payment_method":
                    "Mobile Money",

                "paid_at":
                    paid_at.isoformat(),

                "status":
                    "active",

                "starts_at":
                    starts_at.isoformat(),

                "expires_at":
                    expires_at.isoformat()

            })

            .eq(
                "id",
                promotion_id
            )

            .execute()

        )


        if not update_response.data:

            raise HTTPException(

                status_code=500,

                detail=(
                    "MTN payment was successful "
                    "but the promotion could not "
                    "be activated."
                )

            )


        return {

            "promotion_id":
                promotion_id,

            "payment_status":
                "paid",

            "promotion_status":
                "active",

            "mtn_status":
                mtn_result,

            "payment_reference":
                payment_reference,

            "starts_at":
                starts_at.isoformat(),

            "expires_at":
                expires_at.isoformat(),

            "message":
                (
                    "Payment confirmed. "
                    "Promotion is now active."
                )

        }


    # ========================================================
    # FAILED PAYMENT
    # ========================================================

    if mtn_result in [
        "FAILED",
        "REJECTED"
    ]:

        update_response = (

            supabase

            .table(
                "product_promotions"
            )

            .update({

                "payment_status":
                    "failed"

            })

            .eq(
                "id",
                promotion_id
            )

            .execute()

        )


        if not update_response.data:

            raise HTTPException(

                status_code=500,

                detail=(
                    "Payment failed at MTN, "
                    "but the promotion could "
                    "not be updated."
                )

            )


        return {

            "promotion_id":
                promotion_id,

            "payment_status":
                "failed",

            "promotion_status":
                promotion.get(
                    "status"
                ),

            "mtn_status":
                mtn_result,

            "message":
                "Mobile Money payment failed."

        }


    # ========================================================
    # STILL PROCESSING
    # ========================================================

    return {

        "promotion_id":
            promotion_id,

        "payment_status":
            "pending",

        "promotion_status":
            promotion.get(
                "status"
            ),

        "mtn_status":
            mtn_result
            or "PENDING",

        "payment_reference":
            payment_reference,

        "message":
            (
                "Mobile Money payment "
                "is still being processed."
            )

    }


# ============================================================
# GET SUPPLIER PROMOTIONS
#
# GET /promotions/supplier/{seller_id}
# ============================================================

@router.get(
    "/promotions/supplier/{seller_id}"
)
async def get_supplier_promotions(
    seller_id: str
):

    try:

        response = (

            supabase

            .table("product_promotions")

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

        promotions = (
            response.data
            or []
        )


        # ====================================================
        # MARK EXPIRED PROMOTIONS
        # ====================================================

        now = datetime.now(
            timezone.utc
        )


        for promotion in promotions:

            if (
                promotion.get("status")
                == "active"
                and promotion.get(
                    "expires_at"
                )
            ):

                expires_at = datetime.fromisoformat(

                    promotion[
                        "expires_at"
                    ].replace(
                        "Z",
                        "+00:00"
                    )

                )


                if expires_at <= now:

                    promotion["status"] = (
                        "expired"
                    )


        return promotions


    except Exception as e:

        raise HTTPException(

            status_code=500,

            detail=str(e)

        )


# ============================================================
# GET ACTIVE PROMOTIONS
#
# GET /promotions/active
#
# Public marketplace endpoint.
# ============================================================

@router.get(
    "/promotions/active"
)
async def get_active_promotions():

    try:

        now = datetime.now(
            timezone.utc
        ).isoformat()


        response = (

            supabase

            .table(
                "product_promotions"
            )

            .select("*")

            .eq(
                "status",
                "active"
            )

            .eq(
                "payment_status",
                "paid"
            )

            .lte(
                "starts_at",
                now
            )

            .gt(
                "expires_at",
                now
            )

            .order(
                "created_at",
                desc=True
            )

            .execute()

        )


        return response.data or []


    except Exception as e:

        raise HTTPException(

            status_code=500,

            detail=str(e)

        )


# ============================================================
# CANCEL PROMOTION
#
# POST /promotions/{promotion_id}/cancel
# ============================================================

@router.post(
    "/promotions/{promotion_id}/cancel"
)
async def cancel_promotion(
    promotion_id: str
):

    try:

        response = (

            supabase

            .table(
                "product_promotions"
            )

            .update({

                "status":
                    "cancelled"

            })

            .eq(
                "id",
                promotion_id
            )

            .execute()

        )


        if not response.data:

            raise HTTPException(

                status_code=404,

                detail=(
                    "Promotion not found."
                )

            )


        return {

            "message":
                "Promotion cancelled successfully",

            "promotion":
                response.data[0]

        }


    except HTTPException:

        raise


    except Exception as e:

        raise HTTPException(

            status_code=500,

            detail=str(e)

        )


# ============================================================
# EXPIRE PROMOTION
#
# POST /promotions/{promotion_id}/expire
#
# Internal/admin utility for now.
# ============================================================

@router.post(
    "/promotions/{promotion_id}/expire"
)
async def expire_promotion(
    promotion_id: str
):

    try:

        response = (

            supabase

            .table(
                "product_promotions"
            )

            .update({

                "status":
                    "expired"

            })

            .eq(
                "id",
                promotion_id
            )

            .execute()

        )


        if not response.data:

            raise HTTPException(

                status_code=404,

                detail=(
                    "Promotion not found."
                )

            )


        return {

            "message":
                "Promotion expired successfully",

            "promotion":
                response.data[0]

        }


    except HTTPException:

        raise


    except Exception as e:

        raise HTTPException(

            status_code=500,

            detail=str(e)

        )

