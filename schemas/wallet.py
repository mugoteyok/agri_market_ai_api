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
