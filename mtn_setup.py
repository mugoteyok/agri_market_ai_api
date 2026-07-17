import requests
import uuid
import os


SUBSCRIPTION_KEY = os.getenv(
    "MTN_SUBSCRIPTION_KEY"
)


BASE_URL = "https://sandbox.momodeveloper.mtn.com"


API_USER = str(uuid.uuid4())



def create_api_user():

    url = (
        f"{BASE_URL}/v1_0/apiuser"
    )


    headers = {

        "X-Reference-Id": API_USER,

        "Ocp-Apim-Subscription-Key":
            SUBSCRIPTION_KEY,

        "Content-Type":
            "application/json"

    }


    body = {

        "providerCallbackHost":
        "https://agri-market-ai-api.onrender.com"

    }



    response = requests.post(

        url,

        headers=headers,

        json=body

    )



    print(
        "CREATE USER STATUS:",
        response.status_code
    )


    print(
        response.text
    )



    if response.status_code == 201:

        print(
            "API USER CREATED:"
        )

        print(
            API_USER
        )



create_api_user()
