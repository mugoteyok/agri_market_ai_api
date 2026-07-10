from fastapi import APIRouter
from database import supabase
from datetime import datetime


router = APIRouter()


# ===============================
# CREATE PRODUCT LISTING
# ===============================

@router.post("/products")
async def create_product(data: dict):

    product = {

        "farmer_id": data["farmer_id"],

        "crop": data["crop"],

        "description": data.get(
            "description",
            ""
        ),

        "quantity": data["quantity"],

        "unit": data.get(
            "unit",
            "kg"
        ),

        "price_per_unit": data["price_per_unit"],

        "region": data["region"],

        "image_url": data.get(
            "image_url",
            None
        ),

        "status": "available",

        "created_at": datetime.utcnow().isoformat()

    }


    response = (
        supabase
        .table("products")
        .insert(product)
        .execute()
    )


    return {

        "message":
        "Product listed successfully",

        "product":
        response.data

    }



# ===============================
# GET ALL PRODUCTS
# ===============================

@router.get("/products")
async def get_products():


    response = (

        supabase
        .table("products")
        .select("*")
        .eq(
            "status",
            "available"
        )
        .order(
            "created_at",
            desc=True
        )
        .execute()

    )


    return response.data



# ===============================
# FARMER PRODUCTS
# ===============================

@router.get("/products/farmer/{farmer_id}")
async def farmer_products(
    farmer_id:str
):


    response = (

        supabase
        .table("products")
        .select("*")
        .eq(
            "farmer_id",
            farmer_id
        )
        .execute()

    )


    return response.data
