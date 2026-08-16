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
# sandbox
# mtnuganda
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
).rstrip("/")


# ============================================================
# CALLBACK URL
# ============================================================

MTN_CALLBACK_URL = os.getenv(
    "MTN_CALLBACK_URL",
    "https://agri-market-ai-api.onrender.com/"
)


# ============================================================
# CURRENCY
#
# Sandbox uses EUR.
# Production Uganda should use UGX.
# ============================================================

MTN_CURRENCY = os.getenv(
    "MTN_CURRENCY",
    "EUR"
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
            credentials.encode("utf-8")
        )
        .decode("utf-8")
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

    try:

        response = requests.post(
            url,
            headers=headers,
            timeout=30
        )

    except requests.RequestException as e:

        raise Exception(
            "Unable to connect to MTN "
            f"token service: {str(e)}"
        )

    if response.status_code != 200:

        raise Exception(
            "Failed to get MTN access token: "
            f"{response.status_code} "
            f"{response.text}"
        )

    data = response.json()

    access_token = data.get(
        "access_token"
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
#
# Returns:
#
# {
#     "accepted": True/False,
#     "status_code": ...,
#     "reference_id": ...,
#     "external_id": ...,
#     "response_text": ...
# }
# ============================================================

def request_payment(

    amount: float,

    phone_number: str,

    external_id: str,

    payer_message: str,

    payee_note: str,

):

    validate_mtn_config()

    if amount <= 0:

        raise Exception(
            "Payment amount must be greater than zero."
        )

    if not phone_number:

        raise Exception(
            "Mobile Money phone number is required."
        )

    access_token = (
        get_access_token()
    )

    # ========================================================
    # THIS IS THE MTN TRANSACTION REFERENCE
    #
    # It must be a unique UUID.
    #
    # Save this value in your database.
    # ========================================================

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

    }

    # ========================================================
    # CALLBACK
    #
    # Only include this if configured.
    # ========================================================

    if MTN_CALLBACK_URL:

        headers[
            "X-Callback-Url"
        ] = MTN_CALLBACK_URL


    body = {

        "amount":
            str(amount),

        "currency":
            MTN_CURRENCY,

        # Your application's transaction ID.
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

    try:

        response = requests.post(
            url,
            headers=headers,
            json=body,
            timeout=30
        )

    except requests.RequestException as e:

        raise Exception(
            "Unable to connect to MTN "
            f"payment service: {str(e)}"
        )

    return {

        "accepted":
            response.status_code == 202,

        "status_code":
            response.status_code,

        # Save this.
        "reference_id":
            reference_id,

        # Your application's reference.
        "external_id":
            external_id,

        "response_text":
            response.text,

    }


# ============================================================
# GET PAYMENT STATUS
#
# IMPORTANT:
#
# reference_id must be the MTN X-Reference-Id,
# NOT the application's external_id.
# ============================================================

def get_payment_status(

    reference_id: str

):

    validate_mtn_config()

    if not reference_id:

        raise Exception(
            "MTN payment reference is required."
        )

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

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=30
        )

    except requests.RequestException as e:

        raise Exception(
            "Unable to connect to MTN "
            f"payment status service: {str(e)}"
        )

    if response.status_code != 200:

        raise Exception(

            "Failed to get MTN payment status: "

            f"{response.status_code} "

            f"{response.text}"

        )

    return response.json()
