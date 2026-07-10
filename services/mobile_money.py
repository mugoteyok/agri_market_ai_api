import uuid
from datetime import datetime



def request_withdrawal(

    phone,

    amount,

    provider

):


    transaction_id = str(
        uuid.uuid4()
    )


    return {


        "transaction_id":
        transaction_id,


        "phone":
        phone,


        "amount":
        amount,


        "provider":
        provider,


        "status":
        "PENDING",


        "created_at":
        datetime.utcnow()

    }





def check_payment_status(
    transaction_id
):


    return {


        "transaction_id":
        transaction_id,


        "status":
        "COMPLETED"

    }
