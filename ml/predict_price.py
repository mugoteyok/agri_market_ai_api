import joblib
import pandas as pd
import os



MODEL_PATH = "models/price_model.pkl"



model = None
crop_encoder = None
region_encoder = None
demand_encoder = None



# =====================================
# LOAD AI MODEL
# =====================================


if os.path.exists(MODEL_PATH) and os.path.getsize(MODEL_PATH) > 0:

    try:

        model_data = joblib.load(MODEL_PATH)


        model = model_data.get("model")

        crop_encoder = model_data.get(
            "crop_encoder"
        )

        region_encoder = model_data.get(
            "region_encoder"
        )

        demand_encoder = model_data.get(
            "demand_encoder"
        )


        print(
            "✅ Market price AI model loaded successfully"
        )


    except Exception as e:

        print(
            f"⚠️ Model loading failed: {e}"
        )


        model = None



else:

    print(
        "⚠️ Market price model not available"
    )





# =====================================
# PREDICT PRICE
# =====================================


def predict_market_price(

    crop: str,

    region: str,

    month: int,

    rainfall: float,

    demand: str

):


    if model is None:

        raise Exception(
            "Market price AI model is not ready"
        )



    try:


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


            "crop":
            crop_value,


            "region":
            region_value,


            "month":
            month,


            "rainfall":
            rainfall,


            "demand":
            demand_value


        }])




        prediction = model.predict(

            input_data

        )



        return round(

            float(prediction[0]),

            2

        )




    except Exception as e:


        raise Exception(

            str(e)

        )
