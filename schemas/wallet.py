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
        description="Amount earned",
    )

    reference_id: str | None = None

    description: str = "Marketplace sale"


# =====================================
# WITHDRAWAL REQUEST
# =====================================
#
# CANONICAL IDENTITY:
#
#     seller_id
#     seller_type
#
# Backward compatibility:
#
#     farmer_id
#
# Older farmer Flutter code may still
# send farmer_id.
#
# New Flutter code sends seller_id.
# =====================================

class WithdrawalCreate(BaseModel):

    # =================================
    # CANONICAL SELLER ID
    # =================================
    #
    # Farmer:
    #     farmer UUID
    #
    # Supplier:
    #     supplier UUID
    #

    seller_id: str | None = Field(
        default=None,
        description=(
            "UUID of the seller making "
            "the withdrawal"
        ),
    )

    # =================================
    # LEGACY FARMER ID
    # =================================
    #
    # Retained temporarily so older
    # farmer clients do not break.
    #
    # New code should use seller_id.
    #

    farmer_id: str | None = Field(
        default=None,
        description=(
            "Legacy farmer UUID. "
            "Used only when seller_id "
            "is not supplied."
        ),
    )

    # =================================
    # AMOUNT
    # =================================

    amount: float = Field(
        ...,
        gt=0,
        description="Amount to withdraw",
    )

    # =================================
    # MOBILE NUMBER
    # =================================

    mobile_number: str = Field(
        ...,
        min_length=10,
        max_length=15,
    )

    # =================================
    # NETWORK
    # =================================

    network: MobileNetwork

    # =================================
    # SELLER TYPE
    # =================================
    #
    # farmer
    # supplier
    #
    # Defaults to farmer so existing
    # farmer requests remain compatible.
    #

    seller_type: str = Field(
        default="farmer",
        description=(
            "Wallet seller type: "
            "farmer or supplier"
        ),
    )
