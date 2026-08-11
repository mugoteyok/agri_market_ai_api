from fastapi import APIRouter, HTTPException

from database import supabase

from schemas.product import ProductCreate

from datetime import datetime


router = APIRouter()


# ============================================================
# CREATE PRODUCT LISTING
#
# POST /products
#
# Supports:
#
# Farmer:
#   seller_type = farmer
#   product_type = produce
#
# Supplier:
#   seller_type = supplier
#   product_type = supply
# ============================================================

@router.post("/products")
async def create_product(
    product: ProductCreate
):

    # ========================================================
    # DETERMINE SELLER
    # ========================================================

    seller_id = (
        product.seller_id
        or product.farmer_id
    )

    if not seller_id:

        raise HTTPException(
            status_code=400,
            detail="Seller ID is required"
        )

    seller_type = (
        product.seller_type
        or "farmer"
    )

    product_type = (
        product.product_type
        or "produce"
    )

    # Normalize values

    seller_type = seller_type.lower().strip()

    product_type = product_type.lower().strip()


    # ========================================================
    # FARMER COMPATIBILITY
    # ========================================================

    # Existing farmer requests may only send:
    #
    # farmer_id = farmer's user ID
    #
    # We preserve that behavior.

    farmer_id = product.farmer_id

    if seller_type == "farmer":

        if not farmer_id:

            farmer_id = seller_id


    # ========================================================
    # SUPPLIER COMPATIBILITY
    # ========================================================

    # Suppliers do not use farmer_id.

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
                "pesticide, equipment, "
                "other_input, or supply."
            )
        )


    # ========================================================
    # SELLER / PRODUCT COMPATIBILITY
    # ========================================================

    # Farmers currently sell produce.

    if (
        seller_type == "farmer"
        and product_type != "produce"
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                "Farmers can currently list "
                "produce only."
            )
        )


    # Suppliers sell farm supplies.

    if (
        seller_type == "supplier"
        and product_type != "supply"
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                "Suppliers must list "
                "farm supplies using "
                "product_type='supply'."
            )
        )


    # ========================================================
    # VALIDATE QUANTITY
    # ========================================================

    if product.quantity <= 0:

        raise HTTPException(
            status_code=400,
            detail="Quantity must be greater than zero."
        )


    # ========================================================
    # VALIDATE PRICE
    # ========================================================

    if product.price_per_unit <= 0:

        raise HTTPException(
            status_code=400,
            detail="Price must be greater than zero."
        )


    # ========================================================
    # SUPPLIER PRODUCT NAME
    # ========================================================

    # For suppliers, product_name should normally be
    # available.
    #
    # We keep crop as the compatibility field.

    product_name = (
        product.product_name
        or product.crop
    )


    # ========================================================
    # STATUS
    # ========================================================

    status = (
        product.status
        or "available"
    )

    status = status.lower().strip()

    allowed_statuses = [

        "available",

        "sold",

        "unavailable"

    ]

    if status not in allowed_statuses:

        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid product status. "
                "Use available, sold, "
                "or unavailable."
            )
        )


    # ========================================================
    # CREATE PRODUCT DATA
    # ========================================================

    product_data = {

        # ====================================================
        # EXISTING FARMER ARCHITECTURE
        # ====================================================

        "farmer_id":
            farmer_id,


        # ====================================================
        # UNIVERSAL SELLER ARCHITECTURE
        # ====================================================

        "seller_id":
            seller_id,

        "seller_type":
            seller_type,

        "product_type":
            product_type,


        # ====================================================
        # PRODUCT INFORMATION
        # ====================================================

        "crop":
            product.crop,

        "product_name":
            product_name,

        "description":
            product.description,


        # ====================================================
        # FARM SUPPLIES INFORMATION
        # ====================================================

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


        # ====================================================
        # INVENTORY
        # ====================================================

        "quantity":
            product.quantity,

        "unit":
            product.unit,


        # ====================================================
        # PRICE
        # ====================================================

        "price_per_unit":
            product.price_per_unit,


        # ====================================================
        # LOCATION
        # ====================================================

        "region":
            product.region,


        # ====================================================
        # IMAGE
        # ====================================================

        "image_url":
            product.image_url,


        # ====================================================
        # PRODUCT STATUS
        # ====================================================

        "status":
            status,


        # ====================================================
        # AI MARKET INTELLIGENCE
        # ====================================================

        "predicted_price":
            product.predicted_price,

        "ai_recommendation":
            product.ai_recommendation,


        # ====================================================
        # TIMESTAMP
        # ====================================================

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

        if not response.data:

            raise HTTPException(
                status_code=500,
                detail="Product could not be created."
            )


        # ====================================================
        # RESPONSE
        # ====================================================

        return {

            "message":
                "Product listed successfully",

            "product":
                response.data[0]

        }


    except HTTPException:

        raise


    except Exception as e:

        raise HTTPException(

            status_code=500,

            detail=str(e)

        )


# ============================================================
# GET AVAILABLE PRODUCTS
#
# GET /products
#
# Returns all available marketplace products.
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
#
# GET /products/produce
#
# Farmer marketplace.
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
#
# GET /products/supplies
#
# Public farm-supplies marketplace.
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
#
# GET /products/farmer/{farmer_id}
#
# Farmer's own listings.
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

            .eq(
                "seller_type",
                "farmer"
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
#
# GET /products/supplier/{supplier_id}
#
# Supplier's own farm-supply listings.
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
# GET SINGLE PRODUCT
#
# GET /products/{product_id}
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
#
# DELETE /products/{product_id}
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


        if not response.data:

            raise HTTPException(

                status_code=404,

                detail="Product not found"

            )


        return {

            "message":
                "Product deleted successfully",

            "product":
                response.data[0]

        }


    except HTTPException:

        raise


    except Exception as e:

        raise HTTPException(

            status_code=500,

            detail=str(e)

        )
