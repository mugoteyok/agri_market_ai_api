from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from database import supabase

from services.mtn_service import (
    request_payment,
    get_payment_status,
    MTN_CURRENCY,
)

from services.notification_service import (
    notify_seller,
    notify_all_farmers,
)

from datetime import (
    datetime,
    timezone,
    timedelta,
)

import uuid


router = APIRouter()


# ============================================================
# REQUEST MODELS
# ============================================================

class PromotionCreate(BaseModel):

    product_id: str

    seller_id: str

    seller_type: str = "supplier"

    promoted_price: float = Field(gt=0)

    duration_days: int = Field(gt=0)


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
# NORMALIZE UGANDA PHONE NUMBER
# ============================================================

def normalize_phone_number(
    phone_number: str
) -> str:

    phone_number = (
        phone_number
        .strip()
        .replace(" ", "")
        .replace("-", "")
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

    if len(phone_number) != 12:

        raise HTTPException(

            status_code=400,

            detail=(
                "Invalid Uganda Mobile "
                "Money number."
            )

        )

    return phone_number


# ============================================================
# CREATE PROMOTION
#
# POST /promotions
# ============================================================

@router.post(
    "/promotions"
)
async def create_promotion(
    promotion: PromotionCreate
):

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

        print(
            "PROMOTION PRODUCT LOOKUP ERROR:",
            repr(e)
        )

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
    # VERIFY PRODUCT OWNER
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
    # VERIFY SUPPLIER PRODUCT
    # ========================================================

    if product.get("seller_type") != "supplier":

        raise HTTPException(

            status_code=400,

            detail=(
                "Only supplier products "
                "can be promoted."
            )

        )

    if product.get("product_type") != "supply":

        raise HTTPException(

            status_code=400,

            detail=(
                "Only farm-supply products "
                "can be promoted."
            )

        )

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
                "Promoted price must be lower "
                "than the original price."
            )

        )

    # ========================================================
    # CALCULATE DISCOUNT
    # ========================================================

    discount_percentage = round(

        (
            (
                original_price
                - promoted_price
            )
            / original_price
        )
        * 100,

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

        print(
            "PROMOTION EXISTING CHECK ERROR:",
            repr(e)
        )

        raise HTTPException(

            status_code=500,

            detail=(
                "Could not check existing "
                "promotion: "
                f"{str(e)}"
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
    #
    # The promotion does NOT start yet.
    #
    # starts_at and expires_at are only assigned
    # after MTN confirms successful payment.
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
            promotion.duration_days,

        "starts_at":
            None,

        "expires_at":
            None,

        "payment_status":
            "pending",

        "payment_reference":
            None,

        "mtn_reference_id":
            None,

        "payment_method":
            None,

        "paid_at":
            None,

        "status":
            "pending",

        "created_at":
            now.isoformat(),

    }

    # ========================================================
    # INSERT PROMOTION
    #
    # DEBUG LOGGING ADDED HERE
    # ========================================================

    try:

        print(
            "PROMOTION INSERT DATA:",
            promotion_data
        )

        response = (

            supabase

            .table(
                "product_promotions"
            )

            .insert(
                promotion_data
            )

            .execute()

        )

    except Exception as e:

        print(
            "PROMOTION INSERT ERROR:",
            repr(e)
        )

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
            MTN_CURRENCY,

        "payment_status":
            "pending",

    }


# ============================================================
# PAY FOR PROMOTION
#
# POST /promotions/{promotion_id}/payment
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
    # PREVENT INVALID STATUS
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
    # CHECK FOR EXISTING PAYMENT
    # ========================================================

    existing_payment_reference = (
        promotion.get(
            "payment_reference"
        )
    )

    existing_mtn_reference = (
        promotion.get(
            "mtn_reference_id"
        )
    )

    if (

        promotion.get("payment_status")
        == "pending"

        and existing_payment_reference

        and existing_mtn_reference

    ):

        return {

            "message":
                "Payment request already exists.",

            "promotion_id":
                promotion_id,

            "amount":
                promotion_fee,

            "currency":
                MTN_CURRENCY,

            "payment_status":
                "pending",

            "payment_reference":
                existing_payment_reference,

            "next_step":
                (
                    "Approve the Mobile Money "
                    "payment and check payment status."
                )

        }

    # ========================================================
    # NORMALIZE PHONE NUMBER
    # ========================================================

    phone_number = normalize_phone_number(
        payment.mobile_number
    )

    # ========================================================
    # CREATE INTERNAL PAYMENT REFERENCE
    # ========================================================

    payment_reference = str(
        uuid.uuid4()
    )

    # ========================================================
    # REQUEST MTN PAYMENT
    # ========================================================

    try:

        mtn_response = request_payment(

            amount=promotion_fee,

            phone_number=phone_number,

            external_id=payment_reference,

            payer_message=(
                "Agri AI Assist "
                "product promotion"
            ),

            payee_note=(
                "Farm supply promotion payment"
            )

        )

    except Exception as e:

        print(
            "PROMOTION MTN PAYMENT ERROR:",
            repr(e)
        )

        raise HTTPException(

            status_code=502,

            detail=(
                "Unable to initiate Mobile Money "
                f"payment: {str(e)}"
            )

        )

    # ========================================================
    # MTN REQUEST ACCEPTED
    # ========================================================

    if not mtn_response.get("accepted"):

        print(
            "PROMOTION MTN PAYMENT FAILED:",
            mtn_response
        )

        raise HTTPException(

            status_code=502,

            detail=(
                "MTN did not accept the payment request. "
                f"Status: {mtn_response.get('status_code')}. "
                f"Response: {mtn_response.get('response_text')}"
            )

        )

    # ========================================================
    # MTN REFERENCE
    # ========================================================

    mtn_reference_id = (
        mtn_response.get(
            "reference_id"
        )
    )

    if not mtn_reference_id:

        raise HTTPException(

            status_code=500,

            detail=(
                "MTN accepted the payment request "
                "but no MTN reference was returned."
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

        "mtn_reference_id":
            mtn_reference_id,

        "payment_method":
            "Mobile Money",

    }

    try:

        payment_update_response = (

            supabase

            .table(
                "product_promotions"
            )

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

        print(
            "PROMOTION PAYMENT UPDATE ERROR:",
            repr(e)
        )

        raise HTTPException(

            status_code=500,

            detail=(
                "MTN accepted the payment request, "
                "but payment information could "
                "not be saved: "
                f"{str(e)}"
            )

        )

    if not payment_update_response.data:

        raise HTTPException(

            status_code=500,

            detail=(
                "MTN accepted the payment request, "
                "but payment information could "
                "not be saved."
            )

        )

    # ========================================================
    # SUCCESS RESPONSE
    # ========================================================

    return {

        "message":
            (
                "Mobile Money payment request "
                "sent successfully."
            ),

        "promotion_id":
            promotion_id,

        "amount":
            promotion_fee,

        "currency":
            MTN_CURRENCY,

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

                update_response = (

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

                if update_response.data:

                    promotion = (
                        update_response.data[0]
                    )

        return {

            "promotion_id":
                promotion_id,

            "payment_status":
                promotion.get(
                    "payment_status"
                ),

            "status":
                promotion.get(
                    "status"
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
                "Promotion payment already confirmed."

        }

    # ========================================================
    # GET MTN REFERENCE
    # ========================================================

    mtn_reference_id = (

        promotion.get(
            "mtn_reference_id"
        )

    )

    if not mtn_reference_id:

        raise HTTPException(

            status_code=400,

            detail=(
                "No MTN payment request "
                "has been initiated for "
                "this promotion."
            )

        )

    # ========================================================
    # QUERY MTN
    # ========================================================

    try:

        mtn_status = get_payment_status(
            mtn_reference_id
        )

    except Exception as e:

        print(
            "PROMOTION MTN STATUS ERROR:",
            repr(e)
        )

        raise HTTPException(

            status_code=502,

            detail=(
                "Unable to check Mobile Money "
                f"payment status: {str(e)}"
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

        duration_days = int(

            promotion.get(
                "duration_days"
            ) or 0

        )

        if duration_days not in PROMOTION_PRICES:

            raise HTTPException(

                status_code=400,

                detail=(
                    "Invalid promotion duration."
                )

            )

        starts_at = paid_at

        expires_at = (

            starts_at

            + timedelta(
                days=duration_days
            )

        )

        # ====================================================
        # GET PRODUCT INFORMATION
        # ====================================================

        product = None

        try:

            product_response = (

                supabase

                .table("products")

                .select(
                    "id, product_name, product_type, "
                    "seller_id, seller_type, price_per_unit"
                )

                .eq(
                    "id",
                    promotion.get("product_id")
                )

                .limit(1)

                .execute()

            )

            if product_response.data:

                product = (
                    product_response.data[0]
                )

        except Exception as e:

            print(
                "PROMOTION PRODUCT LOOKUP ERROR:",
                repr(e),
            )

        product_name = (

            product.get("product_name")

            if product

            else "Farm supply product"

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
                    expires_at.isoformat(),

            })

            .eq(
                "id",
                promotion_id
            )

            .eq(
                "payment_status",
                "pending"
            )

            .execute()

        )

        # ====================================================
        # CHECK WHETHER ANOTHER REQUEST
        # ALREADY ACTIVATED IT
        # ====================================================

        if not update_response.data:

            latest_response = (

                supabase

                .table(
                    "product_promotions"
                )

                .select("*")

                .eq(
                    "id",
                    promotion_id
                )

                .limit(1)

                .execute()

            )

            latest_promotion = (

                latest_response.data[0]

                if latest_response.data

                else promotion

            )

            if (
                latest_promotion.get(
                    "payment_status"
                )
                == "paid"
            ):

                return {

                    "promotion_id":
                        promotion_id,

                    "payment_status":
                        "paid",

                    "status":
                        latest_promotion.get(
                            "status"
                        ),

                    "promotion_status":
                        latest_promotion.get(
                            "status"
                        ),

                    "mtn_status":
                        mtn_result,

                    "payment_reference":
                        latest_promotion.get(
                            "payment_reference"
                        ),

                    "starts_at":
                        latest_promotion.get(
                            "starts_at"
                        ),

                    "expires_at":
                        latest_promotion.get(
                            "expires_at"
                        ),

                    "message":
                        (
                            "Payment confirmed. "
                            "Promotion is already active."
                        )

                }

            raise HTTPException(

                status_code=500,

                detail=(
                    "MTN payment was successful "
                    "but the promotion could not "
                    "be activated."
                )

            )

        # ====================================================
        # PROMOTION HAS JUST BEEN ACTIVATED
        #
        # SEND NOTIFICATIONS
        # ====================================================

        seller_id = (
            promotion.get("seller_id")
        )

        promotion_notification_data = {

            "promotion_id":
                promotion_id,

            "product_id":
                promotion.get(
                    "product_id"
                ),

            "product_name":
                product_name,

            "promotion_type":
                promotion.get(
                    "promotion_type"
                ),

            "original_price":
                promotion.get(
                    "original_price"
                ),

            "promoted_price":
                promotion.get(
                    "promoted_price"
                ),

            "discount_percentage":
                promotion.get(
                    "discount_percentage"
                ),

            "duration_days":
                duration_days,

            "starts_at":
                starts_at.isoformat(),

            "expires_at":
                expires_at.isoformat(),

            "event":
                "promotion_activated",

        }

        # ====================================================
        # NOTIFY SUPPLIER
        # ====================================================

        if seller_id:

            notify_seller(

                seller_id=seller_id,

                notification_type=
                    "promotion_activated",

                title=
                    "Promotion Activated",

                message=(
                    f"Your promotion for "
                    f"{product_name} is now active."
                ),

                data=
                    promotion_notification_data,

            )

        # ====================================================
        # NOTIFY FARMERS
        # ====================================================

        notify_all_farmers(

            notification_type=
                "promoted_farm_supply",

            title=
                "New Promoted Farm Supply",

            message=(
                f"{product_name} is now "
                f"available in Farm Supplies "
                f"with a special promoted price."
            ),

            data=
                promotion_notification_data,

        )

        # ====================================================
        # SUCCESS RESPONSE
        # ====================================================

        return {

            "promotion_id":
                promotion_id,

            "payment_status":
                "paid",

            "status":
                "active",

            "promotion_status":
                "active",

            "mtn_status":
                mtn_result,

            "payment_reference":
                promotion.get(
                    "payment_reference"
                ),

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

            print(
                "PROMOTION FAILED PAYMENT UPDATE ERROR:",
                repr(e)
            )

        return {

            "promotion_id":
                promotion_id,

            "payment_status":
                "failed",

            "status":
                promotion.get(
                    "status"
                ),

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

        "status":
            promotion.get(
                "status"
            ),

        "promotion_status":
            promotion.get(
                "status"
            ),

        "mtn_status":
            mtn_result
            or "PENDING",

        "payment_reference":
            promotion.get(
                "payment_reference"
            ),

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

            .table(
                "product_promotions"
            )

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

                    update_response = (

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
                            promotion["id"]
                        )

                        .execute()

                    )

                    if update_response.data:

                        promotion.update(
                            update_response.data[0]
                        )

        return promotions

    except HTTPException:

        raise

    except Exception as e:

        print(
            "GET SUPPLIER PROMOTIONS ERROR:",
            repr(e)
        )

        raise HTTPException(

            status_code=500,

            detail=str(e)

        )


# ============================================================
# GET ACTIVE PROMOTIONS
#
# GET /promotions/active
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

        print(
            "GET ACTIVE PROMOTIONS ERROR:",
            repr(e)
        )

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

        print(
            "CANCEL PROMOTION ERROR:",
            repr(e)
        )

        raise HTTPException(

            status_code=500,

            detail=str(e)

        )


# ============================================================
# EXPIRE PROMOTION
#
# POST /promotions/{promotion_id}/expire
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

        print(
            "EXPIRE PROMOTION ERROR:",
            repr(e)
        )

        raise HTTPException(

            status_code=500,

            detail=str(e)

        )
