from pydantic import BaseModel
from typing import Optional


class ProductCreate(BaseModel):

    # =====================================
    # SELLER
    # =====================================

    # Kept for existing farmer marketplace
    farmer_id: Optional[str] = None

    # New universal seller fields
    seller_id: Optional[str] = None
    seller_type: Optional[str] = "farmer"

    # produce / seed / fertilizer / pesticide / equipment / other_input
    product_type: Optional[str] = "produce"


    # =====================================
    # PRODUCT
    # =====================================

    # Kept as "crop" for backward compatibility
    crop: str

    description: Optional[str] = ""

    quantity: float

    unit: str = "kg"

    price_per_unit: float

    region: str

    image_url: Optional[str] = None


    # =====================================
    # AI MARKET INTELLIGENCE
    # =====================================

    predicted_price: Optional[float] = None

    ai_recommendation: Optional[str] = None


class ProductResponse(BaseModel):

    id: str

    farmer_id: Optional[str] = None

    seller_id: Optional[str] = None

    seller_type: Optional[str] = None

    product_type: Optional[str] = None

    crop: str

    description: Optional[str] = None

    quantity: float

    unit: str

    price_per_unit: Optional[float] = None

    region: Optional[str] = None

    image_url: Optional[str] = None

    predicted_price: Optional[float] = None

    ai_recommendation: Optional[str] = None

    status: str

    created_at: str
