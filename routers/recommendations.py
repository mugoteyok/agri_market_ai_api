from fastapi import APIRouter, HTTPException, Query
from supabase import create_client
import os

router = APIRouter(
    prefix="/recommendations",
    tags=["Marketplace Recommendations"],
)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY,
)


@router.get("")
def get_supply_recommendations(
    crop: str = Query(...),
    disease: str = Query(...),
    severity: str = Query("moderate"),
):
    try:
        crop_normalized = crop.strip().lower()
        disease_normalized = disease.strip().lower()

        response = (
            supabase
            .table("disease_supply_recommendations")
            .select("*")
            .eq("crop", crop_normalized)
            .eq("disease", disease_normalized)
            .order("priority")
            .execute()
        )

        recommendations = response.data or []

        return {
            "crop": crop_normalized,
            "disease": disease_normalized,
            "severity": severity,
            "recommendations": recommendations,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
