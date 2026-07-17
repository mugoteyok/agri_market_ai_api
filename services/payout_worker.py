from datetime import datetime

from database import supabase
from services.mtn_service import get_transfer_status



def update_withdrawal_status(transaction_id: str):
    """
    Check MTN transfer status and update withdrawal lifecycle.

    processing
        |
        ├── SUCCESSFUL → completed
        |
        └── FAILED → refund wallet + failed
    """



    # =====================================
    # GET WITHDRAWAL RECORD
    # =====================================


    withdrawal_response = (

        supabase
        .table("withdrawals")
        .select("*")
        .eq(
            "transaction_id",
            transaction_id
        )
        .execute()

    )



    if not withdrawal_response.data:


        return {

            "message":
            "Withdrawal not found"

        }




    withdrawal = withdrawal_response.data[0]



    farmer_id = withdrawal["farmer_id"]

    amount = withdrawal["amount"]




    # =====================================
    # CHECK MTN STATUS
    # =====================================


    mtn_status = get_transfer_status(

        transaction_id

    )



    print(
        "MTN STATUS RESPONSE:",
        mtn_status
    )



    status = (

        mtn_status
        .get(
            "status",
            ""
        )
        .upper()

    )





    # =====================================
    # SUCCESSFUL PAYMENT
    # =====================================


    if status == "SUCCESSFUL":



        supabase.table("withdrawals").update({


            "status":

            "completed",



            "financial_transaction_id":

            mtn_status.get(
                "financialTransactionId"
            ),



            "updated_at":

            datetime.utcnow().isoformat()


        }).eq(


            "transaction_id",

            transaction_id


        ).execute()



        return {


            "message":

            "Withdrawal completed",



            "status":

            "completed"


        }







    # =====================================
    # FAILED PAYMENT
    # =====================================


    elif status == "FAILED":




        wallet_response = (

            supabase
            .table("wallets")
            .select("*")
            .eq(
                "farmer_id",
                farmer_id
            )
            .execute()

        )



        if wallet_response.data:



            wallet = wallet_response.data[0]



            current_balance = (

                wallet.get(
                    "balance"
                )
                or 0

            )



            # Refund farmer


            supabase.table("wallets").update({


                "balance":

                current_balance + amount,



                "updated_at":

                datetime.utcnow().isoformat()


            }).eq(


                "farmer_id",

                farmer_id


            ).execute()





        # Update withdrawal


        supabase.table("withdrawals").update({


            "status":

            "failed",



            "updated_at":

            datetime.utcnow().isoformat()


        }).eq(


            "transaction_id",

            transaction_id


        ).execute()




        return {



            "message":

            "Withdrawal failed. Wallet refunded.",



            "status":

            "failed"


        }







    # =====================================
    # STILL PROCESSING
    # =====================================


    else:



        return {


            "message":

            "Withdrawal still processing",



            "status":

            "processing"


        }
