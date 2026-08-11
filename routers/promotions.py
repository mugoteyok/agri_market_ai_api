from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from database import supabase

from datetime import datetime, timedelta, timezone


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
# CREATE PROMOTION
#
# POST /promotions
#
# Promotion starts as PENDING.
#
# Payment will be connected later.
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
            detail="Only suppliers can promote farm-supply products."
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
            detail=f"Could not retrieve product: {str(e)}"
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
            detail="This supplier does not own this product."
        )


    # ========================================================
    # VERIFY SELLER TYPE
    # ========================================================

    if product.get("seller_type") != "supplier":

        raise HTTPException(
            status_code=400,
            detail="Only supplier products can be promoted."
        )


    # ========================================================
    # VERIFY PRODUCT TYPE
    # ========================================================

    if product.get("product_type") != "supply":

        raise HTTPException(
            status_code=400,
            detail="Only farm-supply products can be promoted."
        )


    # ========================================================
    # VERIFY PRODUCT STATUS
    # ========================================================

    if product.get("status") != "available":

        raise HTTPException(
            status_code=400,
            detail="Only available products can be promoted."
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
            detail="Product has an invalid price."
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
                "Promoted price must be lower "
                "than the original price."
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

    duration_days = promotion.duration_days


    if duration_days > 90:

        raise HTTPException(
            status_code=400,
            detail="Promotion duration cannot exceed 90 days."
        )


    # ========================================================
    # DATES
    # ========================================================

    starts_at = datetime.now(
        timezone.utc
    )

    expires_at = (
        starts_at
        + timedelta(
            days=duration_days
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
                "This product already has a "
                "pending or active promotion."
            )
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
            duration_days,

        "starts_at":
            starts_at.isoformat(),

        "expires_at":
            expires_at.isoformat(),

        # Payment is NOT connected yet.
        "payment_status":
            "pending",

        # Promotion is NOT active until payment.
        "status":
            "pending",

        "created_at":
            starts_at.isoformat()
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
            detail=f"Could not create promotion: {str(e)}"
        )


    if not response.data:

        raise HTTPException(
            status_code=500,
            detail="Promotion could not be created."
        )


    # ========================================================
    # RESPONSE
    # ========================================================

    return {

        "message":
            "Promotion created successfully. Payment is required before it becomes active.",

        "promotion":
            response.data[0]

    }


# ============================================================
# GET SUPPLIER PROMOTIONS
#
# GET /promotions/supplier/{seller_id}
# ============================================================

@router.get("/promotions/supplier/{seller_id}")
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

        promotions = response.data or []


        # ====================================================
        # MARK EXPIRED PROMOTIONS
        # ====================================================

        now = datetime.now(
            timezone.utc
        )


        for promotion in promotions:

            if (
                promotion.get("status") == "active"
                and promotion.get("expires_at")
            ):

                expires_at = datetime.fromisoformat(
                    promotion["expires_at"]
                    .replace(
                        "Z",
                        "+00:00"
                    )
                )


                if expires_at <= now:

                    promotion["status"] = "expired"


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

@router.get("/promotions/active")
async def get_active_promotions():

    try:

        now = datetime.now(
            timezone.utc
        ).isoformat()


        response = (

            supabase

            .table("product_promotions")

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

            .table("product_promotions")

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
                detail="Promotion not found."
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

            .table("product_promotions")

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
                detail="Promotion not found."
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
