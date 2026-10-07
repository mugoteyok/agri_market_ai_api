
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
# CANONICAL IDENTITY
#
# The backend should ultimately derive:
#
#     seller_id
#     seller_type
#     mobile_number
#     network
#
# from the authenticated user and their
# profile.
#
# Legacy fields are retained temporarily
# so older Flutter clients do not fail
# validation while the application is
# being migrated.
# =====================================

class WithdrawalCreate(BaseModel):

    # =================================
    # CANONICAL SELLER ID
    # =================================
    #
    # Temporary compatibility field.
    #
    # The withdrawal router should prefer
    # the authenticated Supabase user ID
    # instead of trusting this value.
    #

    seller_id: str | None = Field(
        default=None,
        description=(
            "Legacy seller UUID. "
            "The backend should derive the "
            "seller from the authenticated user."
        ),
    )

    # =================================
    # LEGACY FARMER ID
    # =================================
    #
    # Retained temporarily for older
    # farmer clients.
    #

    farmer_id: str | None = Field(
        default=None,
        description=(
            "Legacy farmer UUID. "
            "Used only for backward compatibility."
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
    # LEGACY MOBILE NUMBER
    # =================================
    #
    # The backend should NOT use a client-
    # supplied number for the new withdrawal
    # flow.
    #
    # The canonical number comes from:
    #
    #     profiles.mobile_money_number
    #
    # This remains optional temporarily so
    # older clients can still reach the
    # endpoint while the migration happens.
    #

    mobile_number: str | None = Field(
        default=None,
        min_length=10,
        max_length=15,
        description=(
            "Legacy Mobile Money number. "
            "New clients should not send this."
        ),
    )

    # =================================
    # LEGACY NETWORK
    # =================================
    #
    # Current V1 MTN disbursement service
    # uses MTN. The backend should determine
    # the provider rather than trusting the
    # Flutter client.
    #

    network: MobileNetwork | None = Field(
        default=None,
        description=(
            "Legacy Mobile Money network. "
            "New clients should not send this."
        ),
    )

    # =================================
    # LEGACY SELLER TYPE
    # =================================
    #
    # New withdrawal requests should derive
    # this from the authenticated user's
    # profile.role.
    #

    seller_type: str | None = Field(
        default=None,
        description=(
            "Legacy seller type. "
            "The backend should derive this "
            "from the authenticated user's role."
        ),
    )

