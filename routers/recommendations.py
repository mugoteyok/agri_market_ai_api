from fastapi import APIRouter, HTTPException, Query
from supabase import create_client
import os


# ============================================================
# ROUTER
# ============================================================

router = APIRouter(
    prefix="/recommendations",
    tags=["Marketplace Recommendations"],
)


# ============================================================
# SUPABASE
# ============================================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "SUPABASE_URL and SUPABASE_KEY environment variables are required."
    )

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY,
)


# ============================================================
# CATEGORY NORMALIZATION
# ============================================================

def normalize_category(value: str) -> str:
    """
    Normalize category names so recommendation categories
    can match supplier marketplace categories.

    Examples:

        Fungicide  -> fungicides
        Fungicides -> fungicides
        Sprayer    -> sprayers
        Sprayers   -> sprayers
        Protective Equipment -> protective equipment
    """

    if not value:
        return ""

    value = value.strip().lower()

    category_aliases = {
        "fungicide": "fungicides",
        "fungicides": "fungicides",

        "sprayer": "sprayers",
        "sprayers": "sprayers",

        "protective equipment": "protective equipment",

        "seed": "seeds",
        "seeds": "seeds",

        "tool": "tools",
        "tools": "tools",

        "equipment": "equipment",
        "irrigation": "irrigation",
        "storage": "storage",

        "soil product": "soil products",
        "soil products": "soil products",
    }

    return category_aliases.get(value, value)


# ============================================================
# GET SUPPLIER PRODUCTS
# ============================================================

def get_supplier_products(category: str):
    """
    Find available supplier marketplace products
    matching the recommendation category.
    """

    normalized_category = normalize_category(category)

    if not normalized_category:
        return []

    try:
        response = (
            supabase
            .table("products")
            .select(
                """
                id,
                product_name,
                category,
                product_type,
                seller_id,
                seller_type,
                brand,
                description,
                quantity,
                unit,
                price_per_unit,
                availability,
                rating,
                supplier_location,
                image_url,
                status,
                created_at
                """
            )
            .eq("product_type", "supply")
            .eq("seller_type", "supplier")
            .execute()
        )

        products = response.data or []

        matching_products = []

        for product in products:

            product_category = normalize_category(
                product.get("category", "")
            )

            product_status = str(
                product.get("status", "")
            ).strip().lower()

            product_availability = str(
                product.get("availability", "")
            ).strip().lower()

            # ------------------------------------------------
            # CATEGORY MATCH
            # ------------------------------------------------

            if product_category != normalized_category:
                continue

            # ------------------------------------------------
            # ONLY SHOW AVAILABLE PRODUCTS
            # ------------------------------------------------

            if product_status and product_status not in {
                "available",
                "active",
                "in_stock",
            }:
                continue

            if product_availability and product_availability not in {
                "available",
                "in_stock",
            }:
                continue

            matching_products.append(product)

        return matching_products

    except Exception as e:
        print(
            f"Error loading supplier products for "
            f"category '{category}': {e}"
        )

        return []


# ============================================================
# GET DISEASE SUPPLY RECOMMENDATIONS
# ============================================================

@router.get("")
def get_supply_recommendations(
    crop: str = Query(...),
    disease: str = Query(...),
    severity: str = Query("moderate"),
):

    try:

        # ====================================================
        # NORMALIZE INPUT
        # ====================================================

        crop_normalized = crop.strip().lower()
        disease_normalized = disease.strip().lower()
        severity_normalized = severity.strip().lower()


        # ====================================================
        # GET AI SUPPLY RECOMMENDATION RULES
        # ====================================================

        response = (
            supabase
            .table("disease_supply_recommendations")
            .select(
                "crop,disease,category,reason,priority"
            )
            .eq("crop", crop_normalized)
            .eq("disease", disease_normalized)
            .execute()
        )

        raw_recommendations = response.data or []


        # ====================================================
        # REMOVE DUPLICATES
        # ====================================================

        unique_recommendations = []

        seen = set()

        for recommendation in raw_recommendations:

            category = recommendation.get("category", "")
            reason = recommendation.get("reason", "")
            priority = recommendation.get("priority", "")

            normalized_category = normalize_category(category)

            # Use category + reason + priority as
            # the duplicate detection key.

            duplicate_key = (
                normalized_category,
                str(reason).strip().lower(),
                str(priority).strip().lower(),
            )

            if duplicate_key in seen:
                continue

            seen.add(duplicate_key)

            unique_recommendations.append(
                recommendation
            )


        # ====================================================
        # ATTACH REAL SUPPLIER PRODUCTS
        # ====================================================

        final_recommendations = []

        for recommendation in unique_recommendations:

            category = recommendation.get(
                "category",
                ""
            )

            reason = recommendation.get(
                "reason",
                ""
            )

            priority = recommendation.get(
                "priority",
                "medium"
            )

            # ----------------------------------------------
            # FIND ACTUAL MARKETPLACE PRODUCTS
            # ----------------------------------------------

            products = get_supplier_products(
                category
            )

            # ----------------------------------------------
            # BUILD CLEAN RESPONSE
            # ----------------------------------------------

            final_recommendations.append(
                {
                    "category": category,
                    "reason": reason,
                    "priority": priority,
                    "products": products,
                }
            )


        # ====================================================
        # RETURN RESPONSE
        # ====================================================

        return {
            "crop": crop_normalized,
            "disease": disease_normalized,
            "severity": severity_normalized,
            "recommendations": final_recommendations,
        }


    except Exception as e:

        print(
            "Supply recommendation error:",
            str(e)
        )

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
