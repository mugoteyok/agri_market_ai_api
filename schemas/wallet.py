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

    # =================================
    # NEW PRIMARY SELLER ID
    # =================================
    #
    # This is now the preferred field.
    #
    # Farmer:
    #     seller_id = farmer UUID
    #
    # Supplier:
    #     seller_id = supplier UUID
    #
    # =================================

    seller_id: str | None = Field(
        default=None,
        description=(
            "UUID of the seller whose wallet "
            "will be withdrawn from"
        )
    )

    # =================================
    # BACKWARD COMPATIBILITY
    # =================================
    #
    # Existing Flutter farmer withdrawal
    # requests may still send farmer_id.
    #
    # Backend will use:
    #
    #     seller_id
    #
    # first, then:
    #
    #     farmer_id
    #
    # as a fallback.
    #
    # =================================

    farmer_id: str | None = Field(
        default=None,
        description=(
            "Legacy farmer UUID. Used as seller_id "
            "fallback for backward compatibility."
        )
    )

    # =================================
    # WITHDRAWAL AMOUNT
    # =================================

    amount: float = Field(
        ...,
        gt=0,
        description="Amount to withdraw"
    )

    # =================================
    # MOBILE MONEY NUMBER
    # =================================

    mobile_number: str = Field(
        ...,
        min_length=10,
        max_length=15
    )

    # =================================
    # MOBILE NETWORK
    # =================================

    network: MobileNetwork

    # =================================
    # SELLER TYPE
    # =================================
    #
    # farmer
    # supplier
    #
    # Defaults to farmer for backward
    # compatibility.
    #
    # =================================

    seller_type: str = Field(
        default="farmer",
        description=(
            "Wallet seller type: farmer or supplier"
        )
    )
