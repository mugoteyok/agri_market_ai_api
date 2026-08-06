from fastapi import APIRouter, HTTPException

from database import supabase

from schemas.product import ProductCreate

from datetime import datetime



router = APIRouter()





# =====================================
# CREATE PRODUCT LISTING
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


        "predicted_price":
        product.predicted_price,


        "ai_recommendation":
        product.ai_recommendation,


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
# GET AVAILABLE PRODUCTS
# =====================================


@router.get("/products")
async def get_products():


    try:


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



    except Exception as e:


        raise HTTPException(

            status_code=500,

            detail=str(e)

        )





# =====================================
# FARMER PRODUCTS
# =====================================


@router.get("/products/farmer/{farmer_id}")
async def farmer_products(

    farmer_id:str

):


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





# =====================================
# SINGLE PRODUCT
# =====================================


@router.get("/products/{product_id}")
async def get_product(

    product_id:str

):


    response=(

        supabase

        .table("products")

        .select("*")

        .eq(

            "id",

            product_id

        )

        .execute()

    )


    if not response.data:


        raise HTTPException(

            status_code=404,

            detail="Product not found"

        )


    return response.data[0]





# =====================================
# DELETE PRODUCT
# =====================================


@router.delete("/products/{product_id}")
async def delete_product(

    product_id:str

):


    response=(

        supabase

        .table("products")

        .delete()

        .eq(

            "id",

            product_id

        )

        .execute()

    )


    return {


        "message":

        "Product deleted successfully",


        "product":

        response.data

    }
