
from pydantic import BaseModel
from typing import Optional


# =====================================
# CREATE ORDER
# =====================================
#
# The buyer only provides:
# - product
# - buyer
# - quantity
#
# Seller information is automatically
# obtained from the products table.
# =====================================

class OrderCreate(BaseModel):

    product_id: str

    buyer_id: str

    quantity: float


# =====================================
# ORDER RESPONSE
# =====================================

class OrderResponse(BaseModel):

    id: str

    product_id: str

    buyer_id: str

    # =====================================
    # FARMER / SELLER
    # =====================================

    farmer_id: Optional[str] = None

    seller_id: Optional[str] = None

    seller_type: Optional[str] = None

    # =====================================
    # PRODUCT TYPE
    # =====================================

    # produce = maize, coffee, beans, etc.
    # supply  = pesticides, fertilizer,
    #           seeds, equipment, etc.

    product_type: Optional[str] = "produce"

    # =====================================
    # ORDER INFORMATION
    # =====================================

    quantity: float

    total_amount: float

    # =====================================
    # PRODUCT INFORMATION
    # =====================================

    crop: Optional[str] = None

    price_per_unit: Optional[float] = None

    image_url: Optional[str] = None

    # =====================================
    # PAYMENT
    # =====================================

    payment_status: str

    payment_method: Optional[str] = None

    # =====================================
    # ORDER STATUS
    # =====================================

    order_status: str

    status: Optional[str] = None

    accepted_at: Optional[str] = None

    # =====================================
    # DATE
    # =====================================

    created_at: str

