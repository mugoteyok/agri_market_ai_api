from fastapi import APIRouter
import joblib
import pandas as pd


router = APIRouter()



# Load ML model

model = joblib.load(
    "models/price_model.pkl"
)



@router.post("/forecast")

async def predict_price(data:dict):


    features=pd.DataFrame([{

        "crop":
        data["crop"],


        "month":
        data["month"],


        "region":
        data["region"],


        "rainfall":
        data["rainfall"]

    }])



    prediction=model.predict(
        features
    )



    return {


        "crop":
        data["crop"],


        "predicted_price":

        float(prediction[0]),


        "message":

        "AI forecast generated"

    }
