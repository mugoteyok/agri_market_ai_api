from fastapi import APIRouter
from pydantic import BaseModel

from ml.predict_price import predict_market_price


router = APIRouter()



class ForecastRequest(BaseModel):

    crop: str

    region: str

    month: int

    rainfall: float

    demand: str




@router.post("/")
def forecast_price(
    data: ForecastRequest
):


    price = predict_market_price(

        crop=data.crop,

        region=data.region,

        month=data.month,

        rainfall=data.rainfall,

        demand=data.demand

    )


    return {

        "crop": data.crop,

        "region": data.region,

        "predicted_price": price,

        "currency": "UGX/kg"

    }
