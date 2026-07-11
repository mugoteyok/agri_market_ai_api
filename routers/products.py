from fastapi import APIRouter, HTTPException

from database import supabase

from schemas.product import ProductCreate

from datetime import datetime



router = APIRouter()





# =====================================
# CREATE PRODUCT LISTING
# POST /api/marketplace/products
# =====================================


@router.post("/products")
async def create_product(
    product: ProductCreate
):


    product_data = {

        "farmer_id":
        product.farmer_id,


        "crop":
        product.crop,


        "description":
        product.description,


        "quantity":
        product.quantity,


        "unit":
        product.unit,


        "price_per_unit":
        product.price_per_unit,


        "region":
        product.region,


        "image_url":
        product.image_url,


        "status":
        "available",


        "created_at":
        datetime.utcnow().isoformat()

    }



    response = (

        supabase

        .table("products")

        .insert(product_data)

        .execute()

    )



    return {


        "message":
        "Product listed successfully",


        "product":
        response.data

    }





# =====================================
# GET ALL MARKETPLACE PRODUCTS
# GET /api/marketplace/products
# =====================================


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





# =====================================
# GET FARMER PRODUCTS
# GET /api/marketplace/products/farmer/{farmer_id}
# =====================================


@router.get("/products/farmer/{farmer_id}")
async def farmer_products(

    farmer_id: str

):


    response = (

        supabase

        .table("products")

        .select("*")

        .eq(

            "farmer_id",

            farmer_id

        )

        .order(

            "created_at",

            desc=True

        )

        .execute()

    )



    return response.data





# =====================================
# GET SINGLE PRODUCT
# GET /api/marketplace/products/{product_id}
# =====================================


@router.get("/products/{product_id}")
async def get_product(

    product_id: str

):


    response = (

        supabase

        .table("products")

        .select("*")

        .eq(

            "id",

            product_id

        )

        .single()

        .execute()

    )



    if not response.data:


        raise HTTPException(

            status_code=404,

            detail="Product not found"

        )



    return response.data





# =====================================
# UPDATE PRODUCT STATUS
# PUT /api/marketplace/products/{product_id}/status
# =====================================


@router.put("/products/{product_id}/status")
async def update_product_status(

    product_id: str,

    status: str

):


    response = (

        supabase

        .table("products")

        .update({

            "status":
            status

        })

        .eq(

            "id",

            product_id

        )

        .execute()

    )



    return {


        "message":
        "Product status updated",


        "product":
        response.data

    }
