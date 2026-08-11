
from pydantic import BaseModel, Field


class PaymentRequest(BaseModel):

    payment_method: str = Field(
        default="Mobile Money",
        example="Mobile Money"
    )

    phone_number: str = Field(
        ...,
        min_length=9,
        max_length=15,
        example="256770123456"
    )

