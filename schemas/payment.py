from pydantic import BaseModel, Field


class PaymentRequest(BaseModel):

    payment_method: str = Field(
        default="Mobile Money",
        example="Mobile Money"
    )
