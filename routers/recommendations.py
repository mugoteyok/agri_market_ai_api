from fastapi import APIRouter, HTTPException, Query

from database import supabase


router = APIRouter()


# ============================================================
# AI FARM SUPPLY RECOMMENDATIONS
#
# Disease diagnosis
#       ↓
# Crop + Disease
#       ↓
# Recommended supply categories
#       ↓
# Available supplier products
#
# GET /recommendations
# ============================================================


@router.get("/recommendations")
async def get_supply_recommendations(
    crop: str = Query(...),
    disease: str = Query(...),
    severity: str = Query("moderate"),
):

    try:

        # ========================================================
        # NORMALIZE AI DIAGNOSIS VALUES
        # ========================================================

        crop_normalized = (
            crop
            .strip()
            .lower()
        )

        disease_normalized = (
            disease
            .strip()
            .lower()
        )

        severity_normalized = (
            severity
            .strip()
            .lower()
        )


        # ========================================================
        # GET RECOMMENDED SUPPLY CATEGORIES
        #
        # From:
        # disease_supply_recommendations
        # ========================================================

        recommendation_response = (
            supabase
            .table("disease_supply_recommendations")
            .select("*")
            .eq(
                "crop",
                crop_normalized
            )
            .eq(
                "disease",
                disease_normalized
            )
            .execute()
        )


        recommendations = (
            recommendation_response.data
            or []
        )


        # ========================================================
        # NO RECOMMENDATIONS FOUND
        # ========================================================

        if not recommendations:

            return {
                "crop": crop_normalized,
                "disease": disease_normalized,
                "severity": severity_normalized,
                "recommendations": [],
                "message": (
                    "No specific farm-supply "
                    "recommendations were found "
                    "for this diagnosis."
                )
            }


        # ========================================================
        # GET AVAILABLE FARM SUPPLIES
        #
        # We retrieve supplier products once and then match
        # them against the recommended categories.
        # ========================================================

        products_response = (
            supabase
            .table("products")
            .select("*")
            .eq(
                "status",
                "available"
            )
            .eq(
                "product_type",
                "supply"
            )
            .eq(
                "seller_type",
                "supplier"
            )
            .execute()
        )


        products = (
            products_response.data
            or []
        )


        # ========================================================
        # BUILD RECOMMENDATION RESPONSE
        # ========================================================

        recommendation_results = []


        for recommendation in recommendations:

            category = (
                recommendation
                .get("category")
                or ""
            )

            category_normalized = (
                category
                .strip()
                .lower()
            )


            # ====================================================
            # MATCH SUPPLIER PRODUCTS
            # ====================================================

            matching_products = []


            for product in products:

                product_category = (
                    product.get("category")
                    or ""
                )

                product_category_normalized = (
                    product_category
                    .strip()
                    .lower()
                )


                if (
                    product_category_normalized
                    == category_normalized
                ):

                    matching_products.append(
                        product
                    )


            # ====================================================
            # ADD RECOMMENDATION
            # ====================================================

            recommendation_results.append({

                "category":
                    category,

                "reason":
                    recommendation.get(
                        "reason"
                    ),

                "priority":
                    recommendation.get(
                        "priority",
                        "medium"
                    ),

                "products":
                    matching_products

            })


        # ========================================================
        # FINAL RESPONSE
        # ========================================================

        return {

            "crop":
                crop_normalized,

            "disease":
                disease_normalized,

            "severity":
                severity_normalized,

            "recommendations":
                recommendation_results

        }


    except Exception as e:

        raise HTTPException(

            status_code=500,

            detail=str(e)

        )
