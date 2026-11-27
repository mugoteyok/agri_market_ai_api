from database import get_admin_supabase
from services.mtn_service import get_transfer_status


def update_withdrawal_status(transaction_id: str):
    "Reconcile reserved withdrawals through the canonical database RPCs."

    admin = get_admin_supabase()
    response = (
        admin.table("withdrawals")
        .select("*")
        .eq("transaction_id", transaction_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        return {"message": "Withdrawal not found"}

    withdrawal = response.data[0]
    current_status = (withdrawal.get("status") or "").strip().lower()
    if current_status in {"completed", "failed"}:
        return {"message": f"Withdrawal already {current_status}", "status": current_status}

    if withdrawal.get("funds_reserved") is not True:
        return {
            "message": "Legacy withdrawal has no active reservation; reconciliation required",
            "status": current_status,
        }

    reference_id = withdrawal.get("mtn_reference_id")
    if not reference_id:
        return {"message": "Withdrawal MTN reference is missing", "status": "reconciliation_required"}

    mtn_status = get_transfer_status(reference_id)
    status = (mtn_status.get("status") or "").strip().upper()

    if status in {"SUCCESSFUL", "SUCCESS"}:
        result = admin.rpc(
            "complete_wallet_withdrawal",
            {
                "p_transaction_id": transaction_id,
                "p_financial_transaction_id": mtn_status.get("financialTransactionId"),
            },
        ).execute().data
        return {"message": "Withdrawal completion processed", "status": "completed", "result": result}

    if status in {"FAILED", "FAILURE"}:
        reason = mtn_status.get("reason") or mtn_status.get("message") or "MTN confirmed transfer failure"
        result = admin.rpc(
            "release_wallet_withdrawal",
            {
                "p_transaction_id": transaction_id,
                "p_failure_reason": str(reason)[:500],
            },
        ).execute().data
        return {"message": "Withdrawal release processed", "status": "failed", "result": result}

    return {"message": "Withdrawal still processing", "status": "processing"}
