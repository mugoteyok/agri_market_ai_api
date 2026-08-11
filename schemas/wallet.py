from pydantic import BaseModel, Field
from enum import Enum


class MobileNetwork(str, Enum):
    MTN = "MTN"
    AIRTEL = "AIRTEL"


# =====================================
# CREATE WALLET
# =====================================

class WalletCreate(BaseModel):

    farmer_id: str


# =====================================
# ADD EARNINGS
# =====================================

class WalletEarning(BaseModel):

    farmer_id: str

    amount: float = Field(
        ...,
        gt=0,
        description="Amount earned"
    )

    reference_id: str | None = None

    description: str = "Marketplace sale"


# =====================================
# WITHDRAWAL REQUEST
# =====================================

class WithdrawalCreate(BaseModel):

    # Kept for backward compatibility.
    #
    # For farmers:
    # this is the farmer UUID.
    #
    # For suppliers/businesses:
    # this contains the seller UUID.
    farmer_id: str

    amount: float = Field(
        ...,
        gt=0,
        description="Amount to withdraw"
    )

    mobile_number: str = Field(
        ...,
        min_length=10,
        max_length=15
    )

    network: MobileNetwork

    # =================================
    # SELLER TYPE
    # =================================
    #
    # farmer  -> existing farmer wallet
    # supplier -> supplier/business wallet
    #
    # Defaults to farmer so existing
    # farmer requests do not change.
    #

    seller_type: str = Field(
        default="farmer",
        description="Wallet seller type: farmer or supplier"
    )
