from pydantic import BaseModel


class PaymentRequest(BaseModel):
    payment_method: str
