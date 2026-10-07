
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

class WithdrawalCreate(BaseModel):
    # Legacy fields retained temporarily for backward compatibility.
    # The withdrawal endpoint no longer trusts these values.
    seller_id: str | None = None
    farmer_id: str | None = None

    # Required withdrawal amount.
    amount: float = Field(
        ...,
        gt=0,
        description="Amount to withdraw",
    )

    # Legacy destination fields retained temporarily.
    # Backend now derives the destination from profiles.mobile_money_number.
    mobile_number: str | None = None
    network: MobileNetwork | None = None

    # Legacy seller type retained temporarily.
    # Backend now derives this from profiles.role.
    seller_type: str | None = None


