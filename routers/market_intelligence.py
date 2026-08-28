
from fastapi import APIRouter, HTTPException, Query

from database import supabase


router = APIRouter()


# ============================================================
# MARKET INTELLIGENCE
#
# GET:
# /api/market-intelligence/{crop_slug}
#
# Calls Supabase RPC:
#
# calculate_market_recommendation(
#     p_crop_slug,
#     p_current_price,
#     p_previous_price,
#     p_trend,
#     p_supply_pressure,
#     p_storage_risk,
#     p_min_price,
#     p_max_price
# )
#
# Supabase project:
#
# xmdjdxwsvvdxwizokhgs
#
# ============================================================


@router.get("/market-intelligence/{crop_slug}")
async def get_market_intelligence(
    crop_slug: str,

    current_price: float = Query(
        ...,
        description="Current market price"
    ),

    previous_price: float | None = Query(
        None,
        description="Previous market price"
    ),

    trend: str = Query(
        "unknown",
        description="Price trend: rising, falling, stable, or unknown"
    ),

    supply_pressure: str = Query(
        "unknown",
        description="Supply pressure: high, medium, low, or unknown"
    ),

    storage_risk: str = Query(
        "unknown",
        description="Storage risk: high, medium, low, or unknown"
    ),

    min_price: float | None = Query(
        None,
        description="Minimum observed market price"
    ),

    max_price: float | None = Query(
        None,
        description="Maximum observed market price"
    ),
):

    # ========================================================
    # BASIC VALIDATION
    # ========================================================

    if current_price <= 0:
        raise HTTPException(
            status_code=400,
            detail="Current price must be greater than zero."
        )

    if previous_price is not None and previous_price < 0:
        raise HTTPException(
            status_code=400,
            detail="Previous price cannot be negative."
        )

    if min_price is not None and min_price < 0:
        raise HTTPException(
            status_code=400,
            detail="Minimum price cannot be negative."
        )

    if max_price is not None and max_price < 0:
        raise HTTPException(
            status_code=400,
            detail="Maximum price cannot be negative."
        )

    if (
        min_price is not None
        and max_price is not None
        and max_price < min_price
    ):
        raise HTTPException(
            status_code=400,
            detail="Maximum price cannot be less than minimum price."
        )

    # ========================================================
    # NORMALIZE INPUTS
    # ========================================================

    crop_slug = crop_slug.strip().lower()

    trend = (
        trend.strip().lower()
        if trend
        else "unknown"
    )

    supply_pressure = (
        supply_pressure.strip().lower()
        if supply_pressure
        else "unknown"
    )

    storage_risk = (
        storage_risk.strip().lower()
        if storage_risk
        else "unknown"
    )

    # ========================================================
    # CALL SUPABASE RPC
    # ========================================================

    try:

        response = (
            supabase
            .rpc(
                "calculate_market_recommendation",
                {
                    "p_crop_slug": crop_slug,
                    "p_current_price": current_price,
                    "p_previous_price": previous_price,
                    "p_trend": trend,
                    "p_supply_pressure": supply_pressure,
                    "p_storage_risk": storage_risk,
                    "p_min_price": min_price,
                    "p_max_price": max_price,
                }
            )
            .execute()
        )

    except Exception as e:

        # Log the complete error to Render logs
        print(
            "============================================================"
        )
        print("MARKET INTELLIGENCE RPC ERROR")
        print(
            "============================================================"
        )
        print(f"Exception type: {type(e).__name__}")
        print(f"Exception: {str(e)}")
        print(
            "============================================================"
        )

        raise HTTPException(
            status_code=500,
            detail={
                "message": "Market intelligence RPC failed.",
                "error_type": type(e).__name__,
                "error": str(e),
            }
        )

    # ========================================================
    # VALIDATE RPC RESPONSE
    # ========================================================

    if response is None:

        print("MARKET INTELLIGENCE ERROR: response is None")

        raise HTTPException(
            status_code=500,
            detail="Market intelligence returned no response."
        )

    # ========================================================
    # DEBUG RESPONSE
    # ========================================================

    print(
        "============================================================"
    )
    print("MARKET INTELLIGENCE RPC RESPONSE")
    print(
        "============================================================"
    )
    print(f"Response data type: {type(response.data).__name__}")
    print(f"Response data: {response.data}")
    print(
        "============================================================"
    )

    # ========================================================
    # VALIDATE DATA
    # ========================================================

    if response.data is None:

        raise HTTPException(
            status_code=500,
            detail="Market intelligence returned no data."
        )

    # ========================================================
    # SUPABASE RPC RETURNS JSONB
    #
    # The SQL function uses JSONB_BUILD_OBJECT(), therefore
    # the Supabase response should already be a Python dict.
    # ========================================================

    result = response.data

    if not isinstance(result, dict):

        raise HTTPException(
            status_code=500,
            detail={
                "message": "Invalid market intelligence response.",
                "response_type": type(result).__name__,
                "response": str(result),
            }
        )

    # ========================================================
    # RETURN RESULT TO FLUTTER
    # ========================================================

    return result

