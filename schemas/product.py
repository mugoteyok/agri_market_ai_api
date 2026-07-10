from pydantic import BaseModel
from typing import Optional


class ProductCreate(BaseModel):

    farmer_id: str

    crop: str

    description: Optional[str] = ""

    quantity: float

    unit: str = "kg"

    price_per_unit: float

    region: str

    image_url: Optional[str] = None
