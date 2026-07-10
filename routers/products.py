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

        "quantity": data["quantity"],

        "price_per_kg": data["price_per_kg"],

        "location": data["location"],

        "created_at": datetime.utcnow()

    }


    response = (
        supabase
        .table("products")
        .insert(product)
        .execute()
    )


    return {

        "message":"Product listed successfully",

        "product":response.data

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
async def farmer_products(farmer_id:str):


    response=(

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
