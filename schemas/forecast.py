from pydantic import BaseModel



class ForecastRequest(BaseModel):

    crop: str

    region: str

    month: int

    rainfall: float

    demand: str





class ForecastResponse(BaseModel):

    crop: str

    region: str

    predicted_price: float

    currency: str = "UGX/kg"

    confidence: float | None = None

    message: str
