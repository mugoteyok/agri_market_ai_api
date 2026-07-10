import joblib
import pandas as pd
import os


MODEL_PATH = "models/price_model.pkl"


# Load AI model

if not os.path.exists(MODEL_PATH):

    raise Exception(
        "price_model.pkl not found. Train model first."
    )


model_data = joblib.load(
    MODEL_PATH
)


model = model_data["model"]

crop_encoder = model_data["crop_encoder"]

region_encoder = model_data["region_encoder"]

demand_encoder = model_data["demand_encoder"]



def predict_market_price(
    crop: str,
    region: str,
    month: int,
    rainfall: float,
    demand: str
):


    # Encode farmer inputs

    crop_value = crop_encoder.transform(
        [crop]
    )[0]


    region_value = region_encoder.transform(
        [region]
    )[0]


    demand_value = demand_encoder.transform(
        [demand]
    )[0]



    input_data = pd.DataFrame([{

        "crop": crop_value,

        "region": region_value,

        "month": month,

        "rainfall": rainfall,

        "demand": demand_value

    }])



    prediction = model.predict(
        input_data
    )



    return round(
        float(prediction[0]),
        2
    )
