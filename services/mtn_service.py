import requests
import os
import base64
from dotenv import load_dotenv


load_dotenv()


# =====================================
# MTN MOMO SANDBOX CONFIGURATION
# =====================================

BASE_URL = "https://sandbox.momodeveloper.mtn.com"


API_USER = os.getenv(
    "MTN_API_USER"
)


API_KEY = os.getenv(
    "MTN_API_KEY"
)


SUBSCRIPTION_KEY = os.getenv(
    "MTN_SUBSCRIPTION_KEY"
)



# =====================================
# VALIDATE CONFIG
# =====================================

def validate_config():

    if not API_USER:
        raise Exception(
            "MTN_API_USER missing"
        )

    if not API_KEY:
        raise Exception(
            "MTN_API_KEY missing"
        )

    if not SUBSCRIPTION_KEY:
        raise Exception(
            "MTN_SUBSCRIPTION_KEY missing"
        )





# =====================================
# GET MTN ACCESS TOKEN
# DISBURSEMENT API
# =====================================

def get_access_token():


    validate_config()


    credentials = (

        f"{API_USER}:{API_KEY}"

    )


    encoded_credentials = base64.b64encode(

        credentials.encode()

    ).decode()



    url = (

        f"{BASE_URL}/disbursement/token/"

    )



    response = requests.post(


        url,


        headers={


            "Authorization":

            f"Basic {encoded_credentials}",


            "Ocp-Apim-Subscription-Key":

            SUBSCRIPTION_KEY,


            "Content-Type":

            "application/json"


        }


    )



    print(
        "TOKEN URL:",
        url
    )


    print(
        "TOKEN STATUS:",
        response.status_code
    )


    print(
        response.text
    )



    if response.status_code != 200:

        raise Exception(
            response.text
        )



    return response.json()["access_token"]







# =====================================
# SEND MONEY TO FARMER
# MTN DISBURSEMENT TRANSFER
# =====================================

def transfer_money(

    amount: float,

    phone_number: str,

    external_id: str

):


    token = get_access_token()



    url = (

        f"{BASE_URL}/disbursement/v1_0/transfer"

    )




    response = requests.post(



        url,



        headers={



            "Authorization":

            f"Bearer {token}",



            "X-Reference-Id":

            external_id,



            "X-Target-Environment":

            "sandbox",



            "Ocp-Apim-Subscription-Key":

            SUBSCRIPTION_KEY,



            "Content-Type":

            "application/json"


        },



        json={



            "amount":

            str(amount),



            "currency":

            "UGX",



            "externalId":

            external_id,



            "payee": {



                "partyIdType":

                "MSISDN",



                "partyId":

                phone_number


            }



        }



    )




    print(
        "TRANSFER URL:",
        url
    )



    print(
        "TRANSFER STATUS:",
        response.status_code
    )



    print(
        response.text
    )



    return response







# =====================================
# GET TRANSFER STATUS
# MTN DISBURSEMENT API
# =====================================

def get_transfer_status(

    reference_id: str

):


    token = get_access_token()



    url = (

        f"{BASE_URL}/disbursement/v1_0/transfer/{reference_id}"

    )




    response = requests.get(



        url,



        headers={



            "Authorization":

            f"Bearer {token}",



            "X-Target-Environment":

            "sandbox",



            "Ocp-Apim-Subscription-Key":

            SUBSCRIPTION_KEY,



            "Content-Type":

            "application/json"


        }



    )




    print(
        "STATUS URL:",
        url
    )



    print(
        "STATUS CODE:",
        response.status_code
    )



    print(
        response.text
    )




    if response.status_code != 200:


        raise Exception(

            response.text

        )




    return response.json()
