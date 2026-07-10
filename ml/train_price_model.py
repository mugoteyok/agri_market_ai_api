import pandas as pd
import joblib
import os

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import LabelEncoder



# Load dataset

data = pd.read_csv(
    "ml/dataset/market_prices.csv"
)



# Encode text values

crop_encoder = LabelEncoder()
region_encoder = LabelEncoder()
demand_encoder = LabelEncoder()



data["crop"] = crop_encoder.fit_transform(
    data["crop"]
)

data["region"] = region_encoder.fit_transform(
    data["region"]
)

data["demand"] = demand_encoder.fit_transform(
    data["demand"]
)



X = data.drop(
    "price",
    axis=1
)


y = data["price"]



X_train,X_test,y_train,y_test = train_test_split(

    X,
    y,
    test_size=0.2,
    random_state=42

)



model = RandomForestRegressor(

    n_estimators=100,

    random_state=42

)



model.fit(

    X_train,

    y_train

)



accuracy = model.score(

    X_test,

    y_test

)


print(
    "Model accuracy:",
    accuracy
)



# Create models folder

os.makedirs(
    "models",
    exist_ok=True
)



# Save everything

joblib.dump(

    {

    "model":model,

    "crop_encoder":crop_encoder,

    "region_encoder":region_encoder,

    "demand_encoder":demand_encoder

    },

    "models/price_model.pkl"

)


print(
    "Price model saved"
)
