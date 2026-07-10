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

    status: str

    created_at: str
