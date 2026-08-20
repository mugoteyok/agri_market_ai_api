import base64
import os
import uuid
import json

import requests


# ============================================================
# MTN CONFIGURATION
# ============================================================

# ------------------------------------------------------------
# COLLECTIONS
#
# Used when a customer/farmer/supplier pays Agri AI Assist.
# ------------------------------------------------------------

MTN_COLLECTION_SUBSCRIPTION_KEY = os.getenv(
    "MTN_COLLECTION_SUBSCRIPTION_KEY"
)


# ------------------------------------------------------------
# DISBURSEMENTS
#
# Used when Agri AI Assist pays a farmer or supplier.
# ------------------------------------------------------------

MTN_DISBURSEMENT_SUBSCRIPTION_KEY = os.getenv(
    "MTN_DISBURSEMENT_SUBSCRIPTION_KEY"
)


# ============================================================
# COLLECTION API USER AND API KEY
# ============================================================

MTN_API_USER = os.getenv(
    "MTN_API_USER"
)

MTN_API_KEY = os.getenv(
    "MTN_API_KEY"
)


# ============================================================
# DISBURSEMENT API USER AND API KEY
# ============================================================

MTN_DISBURSEMENT_API_USER = os.getenv(
    "MTN_DISBURSEMENT_API_USER",
    MTN_API_USER
)

MTN_DISBURSEMENT_API_KEY = os.getenv(
    "MTN_DISBURSEMENT_API_KEY",
    MTN_API_KEY
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
# ============================================================

MTN_BASE_URL = os.getenv(
    "MTN_BASE_URL",
    "https://sandbox.momodeveloper.mtn.com"
).rstrip("/")


# ============================================================
# DISBURSEMENT BASE URL
# ============================================================

MTN_DISBURSEMENT_BASE_URL = os.getenv(
    "MTN_DISBURSEMENT_BASE_URL",
    MTN_BASE_URL
).rstrip("/")


# ============================================================
# CALLBACK URL
#
# This should be configured as an environment variable.
#
# Example:
#
# https://agri-market-ai-api.onrender.com/api/mtn/callback
# ============================================================

MTN_CALLBACK_URL = os.getenv(
    "MTN_CALLBACK_URL",
    ""
).strip()


# ============================================================
# CURRENCY
# ============================================================

MTN_CURRENCY = os.getenv(
    "MTN_CURRENCY",
    "EUR"
)


# ============================================================
# VALIDATE COLLECTIONS CONFIGURATION
# ============================================================

def validate_collection_config():

    missing = []

    if not MTN_COLLECTION_SUBSCRIPTION_KEY:

        missing.append(
            "MTN_COLLECTION_SUBSCRIPTION_KEY"
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
            "Missing MTN Collections environment variables: "
            + ", ".join(missing)
        )


# ============================================================
# VALIDATE DISBURSEMENTS CONFIGURATION
# ============================================================

def validate_disbursement_config():

    missing = []

    if not MTN_DISBURSEMENT_SUBSCRIPTION_KEY:

        missing.append(
            "MTN_DISBURSEMENT_SUBSCRIPTION_KEY"
        )

    if not MTN_DISBURSEMENT_API_USER:

        missing.append(
            "MTN_DISBURSEMENT_API_USER"
        )

    if not MTN_DISBURSEMENT_API_KEY:

        missing.append(
            "MTN_DISBURSEMENT_API_KEY"
        )

    if missing:

        raise Exception(
            "Missing MTN Disbursement environment variables: "
            + ", ".join(missing)
        )


# ============================================================
# GET COLLECTION ACCESS TOKEN
# ============================================================

def get_access_token():

    validate_collection_config()

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
            MTN_COLLECTION_SUBSCRIPTION_KEY,

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
            f"Collections token service: {str(e)}"
        )

    if response.status_code != 200:

        raise Exception(
            "Failed to get MTN Collections access token: "
            f"{response.status_code} "
            f"{response.text}"
        )

    data = response.json()

    access_token = data.get(
        "access_token"
    )

    if not access_token:

        raise Exception(
            "MTN Collections did not return an access token."
        )

    return access_token


# ============================================================
# GET DISBURSEMENT ACCESS TOKEN
# ============================================================

def get_disbursement_access_token():

    validate_disbursement_config()

    credentials = (
        f"{MTN_DISBURSEMENT_API_USER}:"
        f"{MTN_DISBURSEMENT_API_KEY}"
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
            MTN_DISBURSEMENT_SUBSCRIPTION_KEY,

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
            f"Disbursement token service: {str(e)}"
        )

    if response.status_code != 200:

        raise Exception(
            "Failed to get MTN Disbursement "
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
            "MTN Disbursement service did not "
            "return an access token."
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

    validate_collection_config()

    if amount <= 0:

        raise Exception(
            "Payment amount must be greater than zero."
        )

    if not phone_number:

        raise Exception(
            "Mobile Money phone number is required."
        )

    if not external_id:

        raise Exception(
            "External transaction ID is required."
        )

    access_token = get_access_token()

    # --------------------------------------------------------
    # THIS IS THE MTN TRANSACTION REFERENCE.
    #
    # It must later be used when checking payment status.
    # --------------------------------------------------------

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
            MTN_COLLECTION_SUBSCRIPTION_KEY,

        "Content-Type":
            "application/json",

    }

    # --------------------------------------------------------
    # ONLY SEND CALLBACK IF CONFIGURED
    # --------------------------------------------------------

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

    print("========== MTN REQUEST ==========")
    print("URL:", url)
    print("REFERENCE ID:", reference_id)
    print("EXTERNAL ID:", external_id)
    print("CALLBACK URL:", MTN_CALLBACK_URL or "NOT SET")
    print("BODY:", body)
    print("=================================")

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

    # --------------------------------------------------------
    # TRY TO PARSE MTN RESPONSE
    # --------------------------------------------------------

    response_data = None

    try:

        response_data = response.json()

    except Exception:

        response_data = None

    return {

        "accepted":
            response.status_code == 202,

        "status_code":
            response.status_code,

        # IMPORTANT:
        # Save this ID for get_payment_status().
        "reference_id":
            reference_id,

        # This is your own transaction/order ID.
        "external_id":
            external_id,

        "response":
            response_data,

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

    validate_collection_config()

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
            MTN_COLLECTION_SUBSCRIPTION_KEY,

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
# ============================================================

def transfer_money(

    amount: float,

    phone_number: str,

    external_id: str

):

    validate_disbursement_config()

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

    reference_id = str(
        uuid.uuid4()
    )

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
            MTN_DISBURSEMENT_SUBSCRIPTION_KEY,

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
            "Agri AI Assist wallet withdrawal",

        "payeeNote":
            "Agri AI Assist wallet withdrawal",

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
# GET TRANSFER STATUS
# ============================================================

def get_transfer_status(

    reference_id: str

):

    validate_disbursement_config()

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
            MTN_DISBURSEMENT_SUBSCRIPTION_KEY,

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
