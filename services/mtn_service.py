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
# COLLECTION BASE URL
#
# Used when a farmer/customer pays the platform.
# ============================================================

MTN_BASE_URL = os.getenv(
    "MTN_BASE_URL",
    "https://sandbox.momodeveloper.mtn.com"
).rstrip("/")


# ============================================================
# DISBURSEMENT BASE URL
#
# Used when the platform pays a farmer/supplier.
#
# If you use the same MTN host for your environment, this can
# be the same as MTN_BASE_URL.
# ============================================================

MTN_DISBURSEMENT_BASE_URL = os.getenv(
    "MTN_DISBURSEMENT_BASE_URL",
    MTN_BASE_URL
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
# Sandbox may use EUR depending on the MTN sandbox product.
# Production Uganda should normally use UGX.
# ============================================================

MTN_CURRENCY = os.getenv(
    "MTN_CURRENCY",
    "EUR"
)


# ============================================================
# VALIDATE COMMON CONFIGURATION
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
#
# Collection token.
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
# GET DISBURSEMENT ACCESS TOKEN
#
# IMPORTANT:
#
# MTN Collection and Disbursement may use different API
# products/credentials.
#
# If your MTN setup provides a separate disbursement user/key,
# configure:
#
# MTN_DISBURSEMENT_API_USER
# MTN_DISBURSEMENT_API_KEY
#
# Otherwise this falls back to the existing credentials.
# ============================================================

def get_disbursement_access_token():

    validate_mtn_config()

    api_user = os.getenv(
        "MTN_DISBURSEMENT_API_USER",
        MTN_API_USER
    )

    api_key = os.getenv(
        "MTN_DISBURSEMENT_API_KEY",
        MTN_API_KEY
    )

    if not api_user or not api_key:

        raise Exception(
            "Missing MTN disbursement credentials."
        )

    credentials = (
        f"{api_user}:{api_key}"
    )

    encoded_credentials = (
        base64.b64encode(
            credentials.encode("utf-8")
        )
        .decode("utf-8")
    )

    url = (
        f"{MTN_DISBURSEMENT_BASE_URL}"
        "/disbursement/token/"
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
            f"disbursement token service: {str(e)}"
        )

    if response.status_code != 200:

        raise Exception(
            "Failed to get MTN disbursement "
            "access token: "
            f"{response.status_code} "
            f"{response.text}"
        )

    data = response.json()

    access_token = data.get(
        "access_token"
    )

    if not access_token:

        raise Exception(
            "MTN disbursement service did not "
            "return an access token."
        )

    return access_token


# ============================================================
# REQUEST PAYMENT
#
# MTN COLLECTIONS
#
# Farmer/customer -> platform
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

    if MTN_CALLBACK_URL:

        headers[
            "X-Callback-Url"
        ] = MTN_CALLBACK_URL

    body = {

        "amount":
            str(amount),

        "currency":
            MTN_CURRENCY,

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

        "reference_id":
            reference_id,

        "external_id":
            external_id,

        "response_text":
            response.text,

    }


# ============================================================
# GET PAYMENT STATUS
#
# MTN COLLECTIONS
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


# ============================================================
# TRANSFER MONEY
#
# MTN DISBURSEMENTS
#
# Platform -> Farmer/Supplier
#
# This function exists specifically because wallet.py imports:
#
# from services.mtn_service import transfer_money
#
# ============================================================

def transfer_money(

    amount: float,

    phone_number: str,

    external_id: str

):

    validate_mtn_config()

    if amount <= 0:

        raise Exception(
            "Transfer amount must be greater than zero."
        )

    if not phone_number:

        raise Exception(
            "Mobile Money phone number is required."
        )

    if not external_id:

        raise Exception(
            "External transaction ID is required."
        )

    access_token = (
        get_disbursement_access_token()
    )

    # ========================================================
    # MTN DISBURSEMENT REFERENCE
    # ========================================================

    reference_id = str(
        uuid.uuid4()
    )

    # ========================================================
    # DISBURSEMENT REQUEST URL
    # ========================================================

    url = (
        f"{MTN_DISBURSEMENT_BASE_URL}"
        "/disbursement/v1_0/transfer"
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

    if MTN_CALLBACK_URL:

        headers[
            "X-Callback-Url"
        ] = MTN_CALLBACK_URL

    body = {

        "amount":
            str(amount),

        "currency":
            MTN_CURRENCY,

        "externalId":
            external_id,

        "payee": {

            "partyIdType":
                "MSISDN",

            "partyId":
                phone_number,

        },

        "payerMessage":
            "Agri Market wallet withdrawal",

        "payeeNote":
            "Agri Market wallet withdrawal",

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
            f"transfer service: {str(e)}"

        )

    return response


# ============================================================
# GET TRANSFER STATUS
#
# MTN DISBURSEMENTS
# ============================================================

def get_transfer_status(

    reference_id: str

):

    validate_mtn_config()

    if not reference_id:

        raise Exception(
            "MTN transfer reference is required."
        )

    access_token = (
        get_disbursement_access_token()
    )

    url = (

        f"{MTN_DISBURSEMENT_BASE_URL}"

        "/disbursement/v1_0/transfer"

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
            f"transfer status service: {str(e)}"

        )

    if response.status_code != 200:

        raise Exception(

            "Failed to get MTN transfer status: "

            f"{response.status_code} "

            f"{response.text}"

        )

    return response.json()
