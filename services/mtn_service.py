import requests
import os
import base64

from dotenv import load_dotenv


load_dotenv()


# ============================================================
# MTN MOMO CONFIGURATION
# ============================================================

BASE_URL = (
    "https://sandbox.momodeveloper.mtn.com"
)


# ============================================================
# API CREDENTIALS
# ============================================================

API_USER = os.getenv(
    "MTN_API_USER"
)

API_KEY = os.getenv(
    "MTN_API_KEY"
)


# ============================================================
# DISBURSEMENT SUBSCRIPTION KEY
#
# Used when:
#
# Seller withdraws money
#
# Marketplace
#     ↓
# Farmer/Supplier
# ============================================================

DISBURSEMENT_SUBSCRIPTION_KEY = os.getenv(
    "MTN_SUBSCRIPTION_KEY"
)


# ============================================================
# COLLECTION SUBSCRIPTION KEY
#
# Used when:
#
# Buyer pays marketplace
#
# Buyer
#     ↓
# Marketplace
# ============================================================

COLLECTION_SUBSCRIPTION_KEY = os.getenv(
    "MTN_COLLECTION_SUBSCRIPTION_KEY"
)


# ============================================================
# TARGET ENVIRONMENT
# ============================================================

TARGET_ENVIRONMENT = os.getenv(
    "MTN_TARGET_ENVIRONMENT",
    "sandbox"
)


# ============================================================
# VALIDATE COMMON CONFIG
# ============================================================

def validate_common_config():

    if not API_USER:

        raise Exception(
            "MTN_API_USER missing"
        )

    if not API_KEY:

        raise Exception(
            "MTN_API_KEY missing"
        )


# ============================================================
# VALIDATE DISBURSEMENT CONFIG
# ============================================================

def validate_disbursement_config():

    validate_common_config()

    if not DISBURSEMENT_SUBSCRIPTION_KEY:

        raise Exception(
            "MTN_SUBSCRIPTION_KEY missing"
        )


# ============================================================
# VALIDATE COLLECTION CONFIG
# ============================================================

def validate_collection_config():

    validate_common_config()

    if not COLLECTION_SUBSCRIPTION_KEY:

        raise Exception(
            "MTN_COLLECTION_SUBSCRIPTION_KEY missing"
        )


# ============================================================
# BUILD BASIC AUTH HEADER
# ============================================================

def _basic_auth_header():

    credentials = (
        f"{API_USER}:{API_KEY}"
    )

    encoded_credentials = (
        base64.b64encode(
            credentials.encode()
        ).decode()
    )

    return (
        f"Basic {encoded_credentials}"
    )


# ============================================================
# GET DISBURSEMENT ACCESS TOKEN
#
# Seller withdrawals
# ============================================================

def get_access_token():

    validate_disbursement_config()

    url = (
        f"{BASE_URL}/disbursement/token/"
    )

    response = requests.post(

        url,

        headers={

            "Authorization":
                _basic_auth_header(),

            "Ocp-Apim-Subscription-Key":
                DISBURSEMENT_SUBSCRIPTION_KEY,

            "Content-Type":
                "application/json"
        },

        timeout=30
    )

    print(
        "DISBURSEMENT TOKEN URL:",
        url
    )

    print(
        "DISBURSEMENT TOKEN STATUS:",
        response.status_code
    )

    print(
        response.text
    )

    if response.status_code != 200:

        raise Exception(
            response.text
        )

    return response.json()[
        "access_token"
    ]


# ============================================================
# GET COLLECTION ACCESS TOKEN
#
# Buyer payments
# ============================================================

def get_collection_access_token():

    validate_collection_config()

    url = (
        f"{BASE_URL}/collection/token/"
    )

    response = requests.post(

        url,

        headers={

            "Authorization":
                _basic_auth_header(),

            "Ocp-Apim-Subscription-Key":
                COLLECTION_SUBSCRIPTION_KEY,

            "Content-Type":
                "application/json"
        },

        timeout=30
    )

    print(
        "COLLECTION TOKEN URL:",
        url
    )

    print(
        "COLLECTION TOKEN STATUS:",
        response.status_code
    )

    print(
        response.text
    )

    if response.status_code != 200:

        raise Exception(
            response.text
        )

    return response.json()[
        "access_token"
    ]


# ============================================================
# REQUEST PAYMENT
#
# Buyer → Marketplace
#
# MTN COLLECTIONS
#
# This does NOT mean payment is completed.
#
# MTN normally returns:
#
# 202 Accepted
#
# The actual payment must subsequently be checked.
# ============================================================

def request_payment(

    amount: float,

    phone_number: str,

    external_id: str,

    payer_message: str = (
        "Agri AI Assist marketplace payment"
    ),

    payee_note: str = (
        "Marketplace order payment"
    )

):

    token = (
        get_collection_access_token()
    )

    url = (
        f"{BASE_URL}/collection/"
        "v1_0/requesttopay"
    )

    response = requests.post(

        url,

        headers={

            "Authorization":
                f"Bearer {token}",

            "X-Reference-Id":
                external_id,

            "X-Target-Environment":
                TARGET_ENVIRONMENT,

            "Ocp-Apim-Subscription-Key":
                COLLECTION_SUBSCRIPTION_KEY,

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

            "payer": {

                "partyIdType":
                    "MSISDN",

                "partyId":
                    phone_number
            },

            "payerMessage":
                payer_message,

            "payeeNote":
                payee_note
        },

        timeout=30
    )

    print(
        "COLLECTION REQUEST URL:",
        url
    )

    print(
        "COLLECTION REQUEST STATUS:",
        response.status_code
    )

    print(
        response.text
    )

    return response


# ============================================================
# GET PAYMENT STATUS
#
# Buyer → Marketplace
#
# reference_id must be the same UUID used in:
#
# X-Reference-Id
#
# when request_payment() was created.
# ============================================================

def get_payment_status(
    reference_id: str
):

    token = (
        get_collection_access_token()
    )

    url = (
        f"{BASE_URL}/collection/"
        f"v1_0/requesttopay/"
        f"{reference_id}"
    )

    response = requests.get(

        url,

        headers={

            "Authorization":
                f"Bearer {token}",

            "X-Target-Environment":
                TARGET_ENVIRONMENT,

            "Ocp-Apim-Subscription-Key":
                COLLECTION_SUBSCRIPTION_KEY,

            "Content-Type":
                "application/json"
        },

        timeout=30
    )

    print(
        "PAYMENT STATUS URL:",
        url
    )

    print(
        "PAYMENT STATUS CODE:",
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


# ============================================================
# SEND MONEY TO FARMER / SUPPLIER
#
# MTN DISBURSEMENT
#
# This remains for seller withdrawals.
# ============================================================

def transfer_money(

    amount: float,

    phone_number: str,

    external_id: str

):

    token = (
        get_access_token()
    )

    url = (
        f"{BASE_URL}/disbursement/"
        "v1_0/transfer"
    )

    response = requests.post(

        url,

        headers={

            "Authorization":
                f"Bearer {token}",

            "X-Reference-Id":
                external_id,

            "X-Target-Environment":
                TARGET_ENVIRONMENT,

            "Ocp-Apim-Subscription-Key":
                DISBURSEMENT_SUBSCRIPTION_KEY,

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
        },

        timeout=30
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


# ============================================================
# GET TRANSFER STATUS
#
# Seller withdrawal status
# ============================================================

def get_transfer_status(

    reference_id: str

):

    token = (
        get_access_token()
    )

    url = (
        f"{BASE_URL}/disbursement/"
        f"v1_0/transfer/"
        f"{reference_id}"
    )

    response = requests.get(

        url,

        headers={

            "Authorization":
                f"Bearer {token}",

            "X-Target-Environment":
                TARGET_ENVIRONMENT,

            "Ocp-Apim-Subscription-Key":
                DISBURSEMENT_SUBSCRIPTION_KEY,

            "Content-Type":
                "application/json"
        },

        timeout=30
    )

    print(
        "TRANSFER STATUS URL:",
        url
    )

    print(
        "TRANSFER STATUS CODE:",
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
