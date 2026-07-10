from pydantic import BaseModel
from typing import Optional


class WalletCreate(BaseModel):

    farmer_id: str



class WalletResponse(BaseModel):

    id: str

    farmer_id: str

    balance: float



class WithdrawalCreate(BaseModel):

    farmer_id: str

    amount: float

    mobile_number: str

    network: str
