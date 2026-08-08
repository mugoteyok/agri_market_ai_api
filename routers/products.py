from fastapi import APIRouter, HTTPException

from database import supabase

from schemas.product import ProductCreate

from datetime import datetime


router = APIRouter()


# ============================================================
# CREATE PRODUCT LISTING
# ============================================================

@router.post("/products")
async def create_product(
    product: ProductCreate
):

    # ========================================================
    # DETERMINE SELLER
    # ========================================================

    seller_id = product.seller_id or product.farmer_id

    if not seller_id:
        raise HTTPException(
            status_code=400,
            detail="Seller ID is required"
        )

    seller_type = product.seller_type or "farmer"

    product_type = product.product_type or "produce"


    # ========================================================
    # FARMER COMPATIBILITY
    # ========================================================

    # Existing farmer requests only send farmer_id.
    #
    # We preserve that behavior by automatically
    # treating farmer_id as seller_id.

    farmer_id = product.farmer_id

    if seller_type == "farmer":

        if not farmer_id:
            farmer_id = seller_id


    # Suppliers do not need farmer_id.

    if seller_type == "supplier":

        farmer_id = None


    # ========================================================
    # VALIDATE SELLER TYPE
    # ========================================================

    if seller_type not in [
        "farmer",
        "supplier"
    ]:

        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid seller type. "
                "Use farmer or supplier."
            )
        )


    # ========================================================
    # VALIDATE PRODUCT TYPE
    # ========================================================

    allowed_product_types = [

        "produce",

        "seed",

        "fertilizer",

        "pesticide",

        "equipment",

        "other_input",

        "supply"

    ]


    if product_type not in allowed_product_types:

        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid product type. "
                "Use produce, seed, fertilizer, "
                "pesticide, equipment, other_input, "
                "or supply."
            )
        )


    # ========================================================
    # SELLER / PRODUCT COMPATIBILITY
    # ========================================================

    # Farmers currently sell produce.

    if seller_type == "farmer" and product_type != "produce":

        raise HTTPException(
            status_code=400,
            detail=(
                "Farmers can currently list "
                "produce only."
            )
        )


    # Suppliers sell agricultural inputs,
    # equipment and other farm supplies.

    if seller_type == "supplier" and product_type == "produce":

        raise HTTPException(
            status_code=400,
            detail=(
                "Suppliers should list "
                "agricultural inputs or equipment."
            )
        )


    # ========================================================
    # CREATE PRODUCT DATA
    # ========================================================

    product_data = {

        # Existing farmer architecture
        "farmer_id":
            farmer_id,

        # Seller architecture
        "seller_id":
            seller_id,

        "seller_type":
            seller_type,

        "product_type":
            product_type,

        # Existing product fields
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

        # AI market intelligence
        "predicted_price":
            product.predicted_price,

        "ai_recommendation":
            product.ai_recommendation,

        # Farm Supplies
        "product_name":
            product.product_name,

        "category":
            product.category,

        "brand":
            product.brand,

        "availability":
            product.availability or "in_stock",

        "rating":
            product.rating or 0,

        "supplier_location":
            product.supplier_location,

        # Existing status
        "status":
            "available",

        "created_at":
            datetime.utcnow().isoformat()
    }


    # ========================================================
    # INSERT INTO SUPABASE
    # ========================================================

    try:

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


    except Exception as e:

        raise HTTPException(

            status_code=500,

            detail=str(e)

        )


# ============================================================
# GET AVAILABLE PRODUCTS
# ============================================================

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


# ============================================================
# GET PRODUCE PRODUCTS
# ============================================================

@router.get("/products/produce")
async def get_produce_products():

    try:

        response = (

            supabase

            .table("products")

            .select("*")

            .eq(
                "status",
                "available"
            )

            .eq(
                "product_type",
                "produce"
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


# ============================================================
# GET FARM SUPPLIES
# ============================================================

@router.get("/products/supplies")
async def get_farm_supplies():

    try:

        response = (

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


# ============================================================
# GET FARMER PRODUCTS
# ============================================================

@router.get("/products/farmer/{farmer_id}")
async def farmer_products(
    farmer_id: str
):

    try:

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


    except Exception as e:

        raise HTTPException(

            status_code=500,

            detail=str(e)

        )


# ============================================================
# GET SUPPLIER PRODUCTS
# ============================================================

@router.get("/products/supplier/{supplier_id}")
async def supplier_products(
    supplier_id: str
):

    try:

        response = (

            supabase

            .table("products")

            .select("*")

            .eq(
                "seller_id",
                supplier_id
            )

            .eq(
                "seller_type",
                "supplier"
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


# ============================================================
# SINGLE PRODUCT
# ============================================================

@router.get("/products/{product_id}")
async def get_product(
    product_id: str
):

    try:

        response = (

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


    except HTTPException:

        raise


    except Exception as e:

        raise HTTPException(

            status_code=500,

            detail=str(e)

        )


# ============================================================
# DELETE PRODUCT
# ============================================================

@router.delete("/products/{product_id}")
async def delete_product(
    product_id: str
):

    try:

        response = (

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


    except Exception as e:

        raise HTTPException(

            status_code=500,

            detail=str(e)

        )
