
from pydantic import BaseModel
from typing import Optional


# ============================================================
# PRODUCT CREATE
# ============================================================

class ProductCreate(BaseModel):

    # ========================================================
    # SELLER
    # ========================================================

    # Existing farmer marketplace field.
    #
    # Existing farmer requests can continue sending:
    # farmer_id = farmer's user ID
    farmer_id: Optional[str] = None

    # Universal seller architecture.
    #
    # Farmer:
    # seller_type = farmer
    #
    # Supplier:
    # seller_type = supplier
    seller_id: Optional[str] = None

    seller_type: Optional[str] = "farmer"


    # ========================================================
    # PRODUCT TYPE
    # ========================================================

    # Existing supported types:
    #
    # produce
    # seed
    # fertilizer
    # pesticide
    # equipment
    # other_input
    #
    # New marketplace type:
    #
    # supply
    #
    # Existing requests that don't provide this field
    # will continue to default to produce.

    product_type: Optional[str] = "produce"


    # ========================================================
    # PRODUCT
    # ========================================================

    # Kept as required for backward compatibility.
    #
    # Existing produce:
    # crop = "Coffee"
    #
    # Farm Supplies compatibility:
    # crop = "Improved Maize Seed"
    #
    # Later we can make this optional after updating the
    # database/API architecture more broadly.
    crop: str

    description: Optional[str] = ""


    # ========================================================
    # FARM SUPPLIES PRODUCT INFORMATION
    # ========================================================

    # Examples:
    #
    # Improved Maize Seed
    # Knapsack Sprayer
    # Irrigation Pump

    product_name: Optional[str] = None


    # Examples:
    #
    # Seeds
    # Farm Equipment
    # Tools
    # Irrigation
    # Protective Equipment
    # Storage & Harvesting
    # Soil Products

    category: Optional[str] = None


    # Optional manufacturer or brand.

    brand: Optional[str] = None


    # ========================================================
    # QUANTITY
    # ========================================================

    quantity: float

    unit: str = "kg"


    # ========================================================
    # PRICE
    # ========================================================

    price_per_unit: float


    # ========================================================
    # LOCATION
    # ========================================================

    region: str

    supplier_location: Optional[str] = None


    # ========================================================
    # IMAGE
    # ========================================================

    image_url: Optional[str] = None


    # ========================================================
    # FARM SUPPLY AVAILABILITY
    # ========================================================

    # Examples:
    #
    # in_stock
    # out_of_stock
    # limited

    availability: Optional[str] = "in_stock"


    # ========================================================
    # FARM SUPPLY RATING
    # ========================================================

    rating: Optional[float] = 0


    # ========================================================
    # AI MARKET INTELLIGENCE
    # ========================================================

    predicted_price: Optional[float] = None

    ai_recommendation: Optional[str] = None


# ============================================================
# PRODUCT RESPONSE
# ============================================================

class ProductResponse(BaseModel):

    # ========================================================
    # BASIC
    # ========================================================

    id: str


    # ========================================================
    # EXISTING FARMER ARCHITECTURE
    # ========================================================

    farmer_id: Optional[str] = None


    # ========================================================
    # UNIVERSAL SELLER ARCHITECTURE
    # ========================================================

    seller_id: Optional[str] = None

    seller_type: Optional[str] = None

    product_type: Optional[str] = None


    # ========================================================
    # EXISTING PRODUCT INFORMATION
    # ========================================================

    crop: str

    description: Optional[str] = None


    # ========================================================
    # FARM SUPPLIES
    # ========================================================

    product_name: Optional[str] = None

    category: Optional[str] = None

    brand: Optional[str] = None

    availability: Optional[str] = "in_stock"

    rating: Optional[float] = 0

    supplier_location: Optional[str] = None


    # ========================================================
    # QUANTITY / UNIT
    # ========================================================

    quantity: float

    unit: str


    # ========================================================
    # PRICE
    # ========================================================

    price_per_unit: Optional[float] = None


    # ========================================================
    # LOCATION
    # ========================================================

    region: Optional[str] = None


    # ========================================================
    # IMAGE
    # ========================================================

    image_url: Optional[str] = None


    # ========================================================
    # AI MARKET INTELLIGENCE
    # ========================================================

    predicted_price: Optional[float] = None

    ai_recommendation: Optional[str] = None


    # ========================================================
    # STATUS
    # ========================================================

    status: str

    created_at: str

