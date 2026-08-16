import base64
import os
import uuid
import requests


# ============================================================
# MTN CONFIGURATION
# ============================================================

MTN_SUBSCRIPTION_KEY = os.getenv(
    "MTN_SUBSCRIPTION_KEY"
)

MTN_API_USER = os.getenv(
    "MTN_API_USER"
)

MTN_API_KEY = os.getenv(
    "MTN_API_KEY"
)


# ============================================================
# ENVIRONMENT
#
# sandbox = testing
# mtnuganda = Uganda production
# ============================================================

MTN_ENVIRONMENT = os.getenv(
    "MTN_ENVIRONMENT",
    "sandbox"
)


# ============================================================
# BASE URL
# ============================================================

MTN_BASE_URL = os.getenv(
    "MTN_BASE_URL",
    "https://sandbox.momodeveloper.mtn.com"
)


# ============================================================
# CALLBACK URL
# ============================================================

MTN_CALLBACK_URL = os.getenv(
    "MTN_CALLBACK_URL",
    "https://agri-market-ai-api.onrender.com/api/marketplace/payments/mtn/callback"
)


# ============================================================
# VALIDATE CONFIGURATION
# ============================================================

def validate_mtn_config():

    missing = []

    if not MTN_SUBSCRIPTION_KEY:
        missing.append(
            "MTN_SUBSCRIPTION_KEY"
        )

    if not MTN_API_USER:
        missing.append(
            "MTN_API_USER"
        )

    if not MTN_API_KEY:
        missing.append(
            "MTN_API_KEY"
        )

    if missing:

        raise Exception(
            "Missing MTN environment variables: "
            + ", ".join(missing)
        )


# ============================================================
# GET ACCESS TOKEN
# ============================================================

def get_access_token():

    validate_mtn_config()

    credentials = (
        f"{MTN_API_USER}:{MTN_API_KEY}"
    )

    encoded_credentials = (
        base64.b64encode(
            credentials.encode()
        )
        .decode()
    )

    url = (
        f"{MTN_BASE_URL}"
        "/collection/token/"
    )

    headers = {

        "Authorization":
            f"Basic {encoded_credentials}",

        "Ocp-Apim-Subscription-Key":
            MTN_SUBSCRIPTION_KEY,

    }

    response = requests.post(
        url,
        headers=headers,
        timeout=30
    )

    if response.status_code != 200:

        raise Exception(
            "Failed to get MTN access token: "
            f"{response.status_code} "
            f"{response.text}"
        )

    data = response.json()

    access_token = (
        data.get("access_token")
    )

    if not access_token:

        raise Exception(
            "MTN did not return an access token."
        )

    return access_token


# ============================================================
# REQUEST PAYMENT
#
# MTN COLLECTIONS
# ============================================================

def request_payment(

    amount: float,

    phone_number: str,

    external_id: str,

    payer_message: str,

    payee_note: str,

):

    validate_mtn_config()

    access_token = (
        get_access_token()
    )

    reference_id = str(
        uuid.uuid4()
    )

    url = (
        f"{MTN_BASE_URL}"
        "/collection/v1_0/requesttopay"
    )

    headers = {

        "Authorization":
            f"Bearer {access_token}",

        "X-Reference-Id":
            reference_id,

        "X-Target-Environment":
            MTN_ENVIRONMENT,

        "Ocp-Apim-Subscription-Key":
            MTN_SUBSCRIPTION_KEY,

        "Content-Type":
            "application/json",

        "X-Callback-Url":
            MTN_CALLBACK_URL,

    }

    body = {

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
                phone_number,

        },

        "payerMessage":
            payer_message,

        "payeeNote":
            payee_note,

    }

    response = requests.post(

        url,

        headers=headers,

        json=body,

        timeout=30

    )

    # Store the MTN reference ID on the response object
    # so the calling router can save it.

    response.mtn_reference_id = (
        reference_id
    )

    return response


# ============================================================
# GET PAYMENT STATUS
# ============================================================

def get_payment_status(

    reference_id: str

):

    validate_mtn_config()

    access_token = (
        get_access_token()
    )

    url = (

        f"{MTN_BASE_URL}"

        "/collection/v1_0/requesttopay"

        f"/{reference_id}"

    )

    headers = {

        "Authorization":
            f"Bearer {access_token}",

        "X-Target-Environment":
            MTN_ENVIRONMENT,

        "Ocp-Apim-Subscription-Key":
            MTN_SUBSCRIPTION_KEY,

    }

    response = requests.get(

        url,

        headers=headers,

        timeout=30

    )

    if response.status_code != 200:

        raise Exception(

            "Failed to get MTN payment status: "

            f"{response.status_code} "

            f"{response.text}"

        )

    return response.json()
