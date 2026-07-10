import joblib
import pandas as pd



model_data = joblib.load(

    "models/price_model.pkl"

)



model = model_data["model"]

crop_encoder = model_data["crop_encoder"]

region_encoder = model_data["region_encoder"]

demand_encoder = model_data["demand_encoder"]




def predict_price(
    crop,
    region,
    month,
    rainfall,
    demand
):


    input_data = pd.DataFrame([{

        "crop":
        crop_encoder.transform([crop])[0],


        "region":
        region_encoder.transform([region])[0],


        "month":
        month,


        "rainfall":
        rainfall,


        "demand":
        demand_encoder.transform([demand])[0]

    }])


    prediction = model.predict(
        input_data
    )


    return round(
        prediction[0],
        2
    )



# Test

if __name__=="__main__":

    price = predict_price(

        "Coffee",

        "Central",

        8,

        100,

        "High"

    )


    print(
        "Predicted price:",
        price
    )
