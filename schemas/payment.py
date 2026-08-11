from pydantic import BaseModel, Field


class PaymentRequest(BaseModel):

    payment_method: str = Field(
        default="Mobile Money",
        example="Mobile Money"
    )

    mobile_number: str = Field(
        ...,
        example="0772123456",
        description="Uganda Mobile Money phone number"
    )
