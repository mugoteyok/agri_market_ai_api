from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from database import supabase

from services.mtn_service import (
    request_payment,
    get_payment_status
)

from datetime import datetime, timedelta, timezone

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
# CREATE PROMOTION
#
# POST /promotions
#
# Creates a promotion in PENDING state.
#
# IMPORTANT:
# Promotion does NOT start until payment succeeds.
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
                "Only suppliers can promote "
                "farm-supply products."
            )
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

    if product.get("seller_id") != promotion.seller_id:

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
        product.get("price_per_unit") or 0
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
    # DURATION
    # ========================================================

    duration_days = (
        promotion.duration_days
    )

    if duration_days > 90:

        raise HTTPException(
            status_code=400,
            detail=(
                "Promotion duration "
                "cannot exceed 90 days."
            )
        )

    # ========================================================
    # CHECK EXISTING ACTIVE/PENDING PROMOTION
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
    # CREATE PENDING PROMOTION
    #
    # IMPORTANT:
    #
    # We do NOT start the promotion yet.
    #
    # starts_at = None
    # expires_at = None
    #
    # They are assigned after successful payment.
    # ========================================================

    now = datetime.now(
        timezone.utc
    )

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
            duration_days,

        "starts_at":
            None,

        "expires_at":
            None,

        "payment_status":
            "pending",

        "payment_reference":
            None,

        "payment_method":
            "Mobile Money",

        "paid_at":
            None,

        "status":
            "pending",

        "created_at":
            now.isoformat()
    }

    # ========================================================
    # INSERT PROMOTION
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
                "Promotion could not "
                "be created."
            )
        )

    # ========================================================
    # RESPONSE
    # ========================================================

    return {

        "message":
            (
                "Promotion created. "
                "Mobile Money payment is required "
                "before the promotion becomes active."
            ),

        "promotion":
            response.data[0]

    }


# ============================================================
# PAY FOR PROMOTION
#
# POST /promotions/{promotion_id}/payment
#
# Uses existing MTN COLLECTIONS API.
#
# The promotion remains pending until MTN
# confirms the payment.
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

    try:

        promotion_response = (
            supabase
            .table("product_promotions")
            .select("*")
            .eq(
                "id",
                promotion_id
            )
            .execute()
        )

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    if not promotion_response.data:

        raise HTTPException(
            status_code=404,
            detail="Promotion not found."
        )

    promotion = (
        promotion_response.data[0]
    )

    # ========================================================
    # CHECK PROMOTION STATUS
    # ========================================================

    if promotion.get("status") == "active":

        raise HTTPException(
            status_code=400,
            detail=(
                "This promotion is "
                "already active."
            )
        )

    if promotion.get("status") in [
        "cancelled",
        "expired"
    ]:

        raise HTTPException(
            status_code=400,
            detail=(
                "This promotion can "
                "no longer be paid for."
            )
        )

    # ========================================================
    # PREVENT DOUBLE PAYMENT
    # ========================================================

    if promotion.get(
        "payment_status"
    ) == "paid":

        raise HTTPException(
            status_code=400,
            detail=(
                "Promotion has "
                "already been paid."
            )
        )

    # ========================================================
    # EXISTING PAYMENT
    #
    # Don't create another MTN request
    # if one is already pending.
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
                (
                    "Promotion payment "
                    "request already exists."
                ),

            "promotion_id":
                promotion_id,

            "payment_status":
                "pending",

            "payment_reference":
                existing_reference,

            "payment_method":
                "Mobile Money"

        }

    # ========================================================
    # PROMOTION PAYMENT AMOUNT
    #
    # IMPORTANT:
    #
    # We need a promotion price.
    #
    # For now the promotion amount is
    # calculated from duration.
    #
    # Current pricing:
    #
    # 1 day = UGX 5,000
    #
    # This can later be moved into
    # a database/package configuration.
    # ========================================================

    duration_days = int(
        promotion.get(
            "duration_days"
        ) or 0
    )

    if duration_days <= 0:

        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid promotion duration."
            )
        )

    promotion_cost_per_day = 5000

    amount = (
        duration_days
        * promotion_cost_per_day
    )

    if amount <= 0:

        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid promotion "
                "payment amount."
            )
        )

    # ========================================================
    # MOBILE MONEY NUMBER
    # ========================================================

    phone_number = (
        payment.mobile_number
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

    # ========================================================
    # NORMALIZE UGANDA NUMBER
    # ========================================================

    if phone_number.startswith("0"):

        phone_number = (
            "256"
            + phone_number[1:]
        )

    # ========================================================
    # VALIDATE PHONE
    # ========================================================

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

    # ========================================================
    # CREATE PAYMENT REFERENCE
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
    # MTN ACCEPTED REQUEST
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

        "payment_method":
            "Mobile Money",

        "payment_reference":
            payment_reference
    }

    try:

        update_response = (
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

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=(
                "MTN accepted the payment "
                "request, but the promotion "
                f"could not be updated: {str(e)}"
            )
        )

    if not update_response.data:

        raise HTTPException(
            status_code=500,
            detail=(
                "MTN accepted the payment "
                "request, but the promotion "
                "could not be updated."
            )
        )

    # ========================================================
    # RESPONSE
    # ========================================================

    return {

        "message":
            (
                "Mobile Money promotion "
                "payment request sent successfully."
            ),

        "promotion_id":
            promotion_id,

        "amount":
            amount,

        "duration_days":
            duration_days,

        "payment_status":
            "pending",

        "payment_method":
            "Mobile Money",

        "payment_reference":
            payment_reference,

        "next_step":
            (
                "Supplier must approve "
                "the Mobile Money payment."
            )
    }


# ============================================================
# CHECK PROMOTION PAYMENT STATUS
#
# GET /promotions/{promotion_id}/payment-status
#
# This endpoint:
#
# 1. Checks MTN
# 2. Confirms payment
# 3. Activates promotion
# 4. Calculates expiry date
#
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

    try:

        promotion_response = (
            supabase
            .table("product_promotions")
            .select("*")
            .eq(
                "id",
                promotion_id
            )
            .execute()
        )

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    if not promotion_response.data:

        raise HTTPException(
            status_code=404,
            detail="Promotion not found."
        )

    promotion = (
        promotion_response.data[0]
    )

    # ========================================================
    # ALREADY ACTIVE
    # ========================================================

    if (
        promotion.get("status")
        == "active"
        and
        promotion.get("payment_status")
        == "paid"
    ):

        # Check expiry while reading.

        expires_at_value = (
            promotion.get(
                "expires_at"
            )
        )

        if expires_at_value:

            expires_at = (
                datetime.fromisoformat(
                    expires_at_value.replace(
                        "Z",
                        "+00:00"
                    )
                )
            )

            now = datetime.now(
                timezone.utc
            )

            if expires_at <= now:

                expired_response = (
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

                return {

                    "promotion_id":
                        promotion_id,

                    "payment_status":
                        "paid",

                    "status":
                        "expired",

                    "message":
                        (
                            "Promotion "
                            "has expired."
                        ),

                    "promotion":
                        (
                            expired_response
                            .data[0]
                            if expired_response.data
                            else promotion
                        )
                }

        return {

            "promotion_id":
                promotion_id,

            "payment_status":
                "paid",

            "status":
                "active",

            "expires_at":
                promotion.get(
                    "expires_at"
                ),

            "message":
                "Promotion is active."

        }

    # ========================================================
    # GET PAYMENT REFERENCE
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
    # ========================================================

    try:

        mtn_status = (
            get_payment_status(
                payment_reference
            )
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
    # PAYMENT SUCCESSFUL
    # ========================================================

    if mtn_result == "SUCCESSFUL":

        now = datetime.now(
            timezone.utc
        )

        duration_days = int(
            promotion.get(
                "duration_days"
            ) or 0
        )

        if duration_days <= 0:

            raise HTTPException(
                status_code=400,
                detail=(
                    "Promotion has "
                    "an invalid duration."
                )
            )

        # ====================================================
        # START PROMOTION NOW
        # ====================================================

        starts_at = now

        expires_at = (
            starts_at
            + timedelta(
                days=duration_days
            )
        )

        # ====================================================
        # UPDATE PROMOTION
        # ====================================================

        promotion_update = {

            "payment_status":
                "paid",

            "payment_method":
                "Mobile Money",

            "paid_at":
                now.isoformat(),

            "starts_at":
                starts_at.isoformat(),

            "expires_at":
                expires_at.isoformat(),

            "status":
                "active"
        }

        try:

            update_response = (
                supabase
                .table(
                    "product_promotions"
                )
                .update(
                    promotion_update
                )
                .eq(
                    "id",
                    promotion_id
                )
                .execute()
            )

        except Exception as e:

            raise HTTPException(
                status_code=500,
                detail=(
                    "Payment was successful "
                    "but promotion activation "
                    f"failed: {str(e)}"
                )
            )

        if not update_response.data:

            raise HTTPException(
                status_code=500,
                detail=(
                    "Payment was successful "
                    "but promotion activation "
                    "failed."
                )
            )

        # ====================================================
        # RESPONSE
        # ====================================================

        return {

            "promotion_id":
                promotion_id,

            "payment_status":
                "paid",

            "status":
                "active",

            "mtn_status":
                mtn_result,

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
    # PAYMENT FAILED
    # ========================================================

    if mtn_result in [
        "FAILED",
        "REJECTED"
    ]:

        try:

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

        except Exception as e:

            raise HTTPException(
                status_code=500,
                detail=str(e)
            )

        return {

            "promotion_id":
                promotion_id,

            "payment_status":
                "failed",

            "status":
                "pending",

            "mtn_status":
                mtn_result,

            "message":
                (
                    "Mobile Money promotion "
                    "payment failed."
                )
        }

    # ========================================================
    # PAYMENT STILL PROCESSING
    # ========================================================

    return {

        "promotion_id":
            promotion_id,

        "payment_status":
            "pending",

        "status":
            promotion.get(
                "status"
            ) or "pending",

        "mtn_status":
            mtn_result or "PENDING",

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
            response.data or []
        )

        # ====================================================
        # AUTOMATICALLY MARK EXPIRED PROMOTIONS
        # ====================================================

        now = datetime.now(
            timezone.utc
        )

        for promotion in promotions:

            if (
                promotion.get(
                    "status"
                ) == "active"
                and promotion.get(
                    "expires_at"
                )
            ):

                expires_at = (
                    datetime.fromisoformat(
                        promotion[
                            "expires_at"
                        ].replace(
                            "Z",
                            "+00:00"
                        )
                    )
                )

                if expires_at <= now:

                    try:

                        supabase \
                            .table(
                                "product_promotions"
                            ) \
                            .update({
                                "status":
                                    "expired"
                            }) \
                            .eq(
                                "id",
                                promotion["id"]
                            ) \
                            .execute()

                    except Exception as e:

                        print(
                            "Promotion expiry "
                            "update failed:",
                            str(e)
                        )

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
        )

        now_iso = now.isoformat()

        # ====================================================
        # FIND ACTIVE PROMOTIONS
        # ====================================================

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
                now_iso
            )
            .gt(
                "expires_at",
                now_iso
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

        # ====================================================
        # GET PROMOTION
        # ====================================================

        existing_response = (
            supabase
            .table(
                "product_promotions"
            )
            .select("*")
            .eq(
                "id",
                promotion_id
            )
            .execute()
        )

        if not existing_response.data:

            raise HTTPException(
                status_code=404,
                detail=(
                    "Promotion not found."
                )
            )

        promotion = (
            existing_response.data[0]
        )

        if promotion.get(
            "status"
        ) == "expired":

            raise HTTPException(
                status_code=400,
                detail=(
                    "Promotion has "
                    "already expired."
                )
            )

        if promotion.get(
            "status"
        ) == "cancelled":

            raise HTTPException(
                status_code=400,
                detail=(
                    "Promotion is "
                    "already cancelled."
                )
            )

        # ====================================================
        # CANCEL
        # ====================================================

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
                    "Promotion could "
                    "not be cancelled."
                )
            )

        return {

            "message":
                (
                    "Promotion cancelled "
                    "successfully"
                ),

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
# Internal/admin utility.
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
                (
                    "Promotion expired "
                    "successfully"
                ),

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
