from fastapi import APIRouter, HTTPException

from schemas.forecast import ForecastRequest

from ml.predict_price import predict_market_price

from datetime import datetime



router = APIRouter()





# =====================================
# AI MARKET PRICE FORECAST
# POST /api/marketplace/forecast
# =====================================


@router.post("/forecast")
def forecast_price(

    data: ForecastRequest

):


    try:


        predicted_price = predict_market_price(

            crop=data.crop,

            region=data.region,

            month=data.month,

            rainfall=data.rainfall,

            demand=data.demand

        )



        return {


            "crop":

            data.crop,


            "region":

            data.region,


            "predicted_price":

            predicted_price,


            "currency":

            "UGX/kg",


            "confidence":

            0.85,


            "generated_at":

            datetime.utcnow().isoformat(),


            "message":

            "AI price prediction generated successfully"


        }




    except Exception as e:


        raise HTTPException(

            status_code=500,

            detail=str(e)

        )
