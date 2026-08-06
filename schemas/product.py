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


    # AI MARKET INTELLIGENCE

    predicted_price: Optional[float] = None

    ai_recommendation: Optional[str] = None





class ProductResponse(BaseModel):

    id: str

    farmer_id: str

    crop: str

    description: Optional[str]

    quantity: float

    unit: str

    price_per_unit: float

    region: str

    image_url: Optional[str]

    predicted_price: Optional[float]

    ai_recommendation: Optional[str]

    status: str

    created_at: str
