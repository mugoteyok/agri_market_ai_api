from pydantic import BaseModel, Field, model_validator
from enum import Enum


# ============================================================
# MOBILE NETWORK
# ============================================================

class MobileNetwork(str, Enum):

    MTN = "MTN"
    AIRTEL = "AIRTEL"


# ============================================================
# CREATE WALLET
# ============================================================

class WalletCreate(BaseModel):

    farmer_id: str


# ============================================================
# ADD EARNINGS
# ============================================================

class WalletEarning(BaseModel):

    farmer_id: str

    amount: float = Field(
        ...,
        gt=0,
        description="Amount earned",
    )

    reference_id: str | None = None

    description: str = "Marketplace sale"


# ============================================================
# WITHDRAWAL REQUEST
# ============================================================
#
# Supports:
#
#   farmer
#   supplier
#
# Preferred field:
#
#   seller_id
#
# Backward-compatible field:
#
#   farmer_id
#
# Existing Flutter code can continue sending:
#
# {
#   "farmer_id": "...",
#   "seller_type": "supplier"
# }
#
# New code should preferably send:
#
# {
#   "seller_id": "...",
#   "seller_type": "supplier"
# }
#
# ============================================================

class WithdrawalCreate(BaseModel):

    # ========================================================
    # SELLER ID
    # ========================================================
    #
    # Preferred field.
    #
    # For farmer:
    #   farmer UUID
    #
    # For supplier:
    #   supplier/business UUID
    #
    seller_id: str | None = Field(
        default=None,
        description=(
            "UUID of the seller requesting the withdrawal."
        ),
    )

    # ========================================================
    # FARMER ID
    # ========================================================
    #
    # BACKWARD COMPATIBILITY
    #
    # Existing Flutter applications may still send
    # farmer_id.
    #
    # The backend will treat this as seller_id when
    # seller_id is not supplied.
    #
    farmer_id: str | None = Field(
        default=None,
        description=(
            "Legacy seller UUID field retained for "
            "backward compatibility."
        ),
    )

    # ========================================================
    # AMOUNT
    # ========================================================

    amount: float = Field(
        ...,
        gt=0,
        description="Amount to withdraw in UGX",
    )

    # ========================================================
    # MOBILE NUMBER
    # ========================================================

    mobile_number: str = Field(
        ...,
        min_length=10,
        max_length=15,
        description=(
            "Uganda Mobile Money phone number."
        ),
    )

    # ========================================================
    # NETWORK
    # ========================================================

    network: MobileNetwork

    # ========================================================
    # SELLER TYPE
    # ========================================================
    #
    # farmer
    # supplier
    #
    # Existing farmer requests remain compatible because
    # farmer is the default.
    #

    seller_type: str = Field(
        default="farmer",
        description=(
            "Wallet seller type: farmer or supplier."
        ),
    )

    # ========================================================
    # NORMALIZE AND VALIDATE SELLER ID
    # ========================================================

    @model_validator(mode="after")
    def validate_seller_identity(self):

        # ----------------------------------------------------
        # Normalize seller type
        # ----------------------------------------------------

        self.seller_type = (
            self.seller_type
            or "farmer"
        ).strip().lower()

        # ----------------------------------------------------
        # Validate seller type
        # ----------------------------------------------------

        if self.seller_type not in [
            "farmer",
            "supplier",
        ]:

            raise ValueError(
                "seller_type must be either "
                "'farmer' or 'supplier'."
            )

        # ----------------------------------------------------
        # Determine seller ID
        #
        # Preferred:
        #
        # seller_id
        #
        # Legacy:
        #
        # farmer_id
        # ----------------------------------------------------

        resolved_seller_id = (
            self.seller_id
            or self.farmer_id
        )

        # ----------------------------------------------------
        # Seller ID is mandatory
        # ----------------------------------------------------

        if not resolved_seller_id:

            raise ValueError(
                "seller_id is required. "
                "The legacy farmer_id field may also be "
                "used for backward compatibility."
            )

        # ----------------------------------------------------
        # Normalize both fields
        # ----------------------------------------------------

        resolved_seller_id = (
            resolved_seller_id.strip()
        )

        self.seller_id = resolved_seller_id

        # ----------------------------------------------------
        # Keep farmer_id populated for backward compatibility
        #
        # This means the rest of the existing backend can
        # still access data.farmer_id while we transition
        # to data.seller_id.
        #
        # For suppliers this intentionally contains the
        # supplier UUID as the legacy carrier.
        # ----------------------------------------------------

        if not self.farmer_id:

            self.farmer_id = resolved_seller_id

        return self
