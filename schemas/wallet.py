from pydantic import BaseModel, Field



# =====================================
# WALLET CREATION / EARNINGS
# =====================================

class WalletCreate(BaseModel):

    farmer_id: str

    amount: float = Field(
        default=0,
        ge=0,
        description="Wallet amount"
    )



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

    mobile_number: str

    network: str
