from datetime import datetime, timedelta, timezone

from database import supabase


# ============================================================
# PLAN HELPERS
# ============================================================

def normalize_plan_name(plan_name: str) -> str:
    return (
        plan_name
        .strip()
        .lower()
    )


# ============================================================
# GET PLAN
# ============================================================

def get_plan(plan_id: str):

    response = (
        supabase
        .table("subscription_plans")
        .select("*")
        .eq("id", plan_id)
        .eq("is_active", True)
        .maybe_single()
        .execute()
    )

    if not response.data:
        raise Exception(
            "Subscription plan not found or inactive."
        )

    return response.data


# ============================================================
# GET PLAN BY NAME
# ============================================================

def get_plan_by_name(plan_name: str):

    normalized = normalize_plan_name(
        plan_name
    )

    response = (
        supabase
        .table("subscription_plans")
        .select("*")
        .eq("is_active", True)
        .execute()
    )

    if not response.data:
        raise Exception(
            "No active subscription plans found."
        )

    for plan in response.data:

        name = normalize_plan_name(
            plan.get("name", "")
        )

        if name == normalized:
            return plan

    raise Exception(
        f"Subscription plan '{plan_name}' "
        "was not found."
    )


# ============================================================
# ACTIVATE PAID SUBSCRIPTION
#
# IMPORTANT:
#
# This function must ONLY be called after MTN confirms
# SUCCESSFUL payment.
# ============================================================

def activate_paid_subscription(

    supplier_id: str,

    plan_id: str,

    payment_id: str

):

    plan = get_plan(
        plan_id
    )

    plan_name = normalize_plan_name(
        plan.get("name", "")
    )

    if plan_name == "basic":

        raise Exception(
            "Basic does not require paid activation."
        )

    now = datetime.now(
        timezone.utc
    )

    billing_interval = (
        plan.get("billing_interval")
        or "monthly"
    ).lower()

    if billing_interval == "monthly":

        period_end = (
            now + timedelta(days=30)
        )

    elif billing_interval == "yearly" or \
         billing_interval == "annual":

        period_end = (
            now + timedelta(days=365)
        )

    else:

        # Safe fallback.
        period_end = (
            now + timedelta(days=30)
        )

    # ========================================================
    # CANCEL / EXPIRE EXISTING ACTIVE SUBSCRIPTION
    # ========================================================

    existing = (
        supabase
        .table("subscriptions")
        .select("*")
        .eq(
            "supplier_id",
            supplier_id
        )
        .maybe_single()
        .execute()
    )

    if existing.data:

        supabase \
            .table("subscriptions") \
            .update({
                "status": "cancelled",
                "cancelled_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }) \
            .eq(
                "id",
                existing.data["id"]
            ) \
            .execute()

    # ========================================================
    # CREATE NEW ACTIVE SUBSCRIPTION
    # ========================================================

    subscription = (
        supabase
        .table("subscriptions")
        .insert({

            "supplier_id":
                supplier_id,

            "plan_id":
                plan_id,

            "status":
                "active",

            "started_at":
                now.isoformat(),

            "current_period_start":
                now.isoformat(),

            "current_period_end":
                period_end.isoformat(),

            "auto_renew":
                False,

            "created_at":
                now.isoformat(),

            "updated_at":
                now.isoformat(),

        })
        .execute()
    )

    if not subscription.data:

        raise Exception(
            "Payment was confirmed, but the "
            "subscription could not be activated."
        )

    new_subscription = (
        subscription.data[0]
    )

    # ========================================================
    # LINK PAYMENT TO SUBSCRIPTION
    # ========================================================

    supabase \
        .table("subscription_payments") \
        .update({

            "subscription_id":
                new_subscription["id"],

            "updated_at":
                now.isoformat(),

        }) \
        .eq(
            "id",
            payment_id
        ) \
        .execute()

    return new_subscription
