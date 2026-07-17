from datetime import datetime

from database import supabase
from services.mtn_service import get_transfer_status


def update_withdrawal_status(transaction_id: str):
    """
    Check the latest MTN transfer status and update
    the withdrawal record accordingly.
    """

    # -------------------------------------
    # Get withdrawal from Supabase
    # -------------------------------------

    withdrawal_response = (
        supabase
        .table("withdrawals")
        .select("*")
        .eq("transaction_id", transaction_id)
        .execute()
    )

    if not withdrawal_response.data:
        return {
            "message": "Withdrawal not found"
        }

    withdrawal = withdrawal_response.data[0]

    # -------------------------------------
    # Ask MTN for latest status
    # -------------------------------------

    mtn_status = get_transfer_status(transaction_id)

    print("MTN STATUS:")
    print(mtn_status)

    # MTN usually returns status in the "status" field.
    status = (
        mtn_status.get("status", "")
        .upper()
    )

    # -------------------------------------
    # SUCCESS
    # -------------------------------------

    if status == "SUCCESSFUL":

        supabase.table("withdrawals").update({

            "status": "completed"

        }).eq(

            "transaction_id",
            transaction_id

        ).execute()

        return {

            "message": "Withdrawal completed"

        }

    # -------------------------------------
    # FAILED
    # -------------------------------------

    elif status == "FAILED":

        farmer_id = withdrawal["farmer_id"]
        amount = withdrawal["amount"]

        wallet_response = (
            supabase
            .table("wallets")
            .select("*")
            .eq("farmer_id", farmer_id)
            .execute()
        )

        wallet = wallet_response.data[0]

        current_balance = wallet["balance"]

        # Refund farmer
        supabase.table("wallets").update({

            "balance": current_balance + amount,

            "updated_at": datetime.utcnow().isoformat()

        }).eq(

            "farmer_id",
            farmer_id

        ).execute()

        # Update withdrawal status
        supabase.table("withdrawals").update({

            "status": "failed"

        }).eq(

            "transaction_id",
            transaction_id

        ).execute()

        return {

            "message": "Withdrawal failed. Wallet refunded."

        }

    # -------------------------------------
    # STILL PROCESSING
    # -------------------------------------

    else:

        return {

            "message": "Withdrawal still processing"

        }
