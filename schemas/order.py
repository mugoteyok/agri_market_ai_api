from pydantic import BaseModel
from typing import Optional



class OrderCreate(BaseModel):

    product_id: str

    buyer_id: str

    quantity: float





class OrderResponse(BaseModel):

    id: str

    product_id: str

    buyer_id: str

    farmer_id: str

    quantity: float

    total_amount: float


    crop: Optional[str] = None

    price_per_unit: Optional[float] = None

    image_url: Optional[str] = None


    payment_status: str

    order_status: str

    status: str

    created_at: str
