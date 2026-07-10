from fastapi import APIRouter, HTTPException

from schemas.forecast import ForecastRequest

from ml.predict_price import predict_market_price



router = APIRouter()




# =====================================
# AI MARKET PRICE FORECAST
# =====================================


@router.post("/forecast")
def forecast_price(
    data: ForecastRequest
):


    try:


        price = predict_market_price(

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

            price,


            "currency":

            "UGX/kg",


            "message":

            "AI price prediction generated"

        }



    except Exception as e:



        raise HTTPException(

            status_code=500,

            detail=str(e)

        )
