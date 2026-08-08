from pydantic import BaseModel
from typing import Optional


# =====================================
# CREATE ORDER
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

    farmer_id: Optional[str] = None

    seller_id: Optional[str] = None

    seller_type: Optional[str] = None

    quantity: float

    total_amount: float

    crop: Optional[str] = None

    price_per_unit: Optional[float] = None

    image_url: Optional[str] = None

    payment_status: str

    order_status: str

    status: Optional[str] = None

    payment_method: Optional[str] = None

    accepted_at: Optional[str] = None

    created_at: str
