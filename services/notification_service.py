from database import supabase


# ============================================================
# CREATE NOTIFICATION
# ============================================================

def create_notification(
    user_id: str,
    notification_type: str,
    title: str,
    message: str,
    data: dict | None = None,
):
    """
    Create one notification for one user.

    Notification failures should be handled by the caller
    so they never break the main business operation.
    """

    if not user_id:
        return []

    notification = {
        "user_id": user_id,
        "type": notification_type,
        "title": title,
        "message": message,
        "is_read": False,
        "data": data or {},
    }

    response = (
        supabase
        .table("notifications")
        .insert(notification)
        .execute()
    )

    return response.data or []


# ============================================================
# CREATE NOTIFICATION SAFELY
# ============================================================

def safe_create_notification(
    user_id: str,
    notification_type: str,
    title: str,
    message: str,
    data: dict | None = None,
):
    """
    Notification helper that NEVER raises an exception
    into the main business operation.

    Example:
    If an order was successfully created but the notification
    table has a temporary problem, the order remains successful.
    """

    try:

        return create_notification(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            data=data,
        )

    except Exception as e:

        print(
            "NOTIFICATION ERROR:",
            str(e),
        )

        return []


# ============================================================
# NOTIFY ALL FARMERS
# ============================================================

def notify_all_farmers(
    notification_type: str,
    title: str,
    message: str,
    data: dict | None = None,
):
    """
    Send notification to all farmer profiles.
    """

    try:

        response = (
            supabase
            .table("profiles")
            .select("id")
            .eq("role", "farmer")
            .execute()
        )

        farmers = response.data or []

        created = []

        for farmer in farmers:

            result = safe_create_notification(

                user_id=farmer["id"],

                notification_type=
                    notification_type,

                title=title,

                message=message,

                data=data,
            )

            created.extend(result)

        return created

    except Exception as e:

        print(
            "FARMER NOTIFICATION ERROR:",
            str(e),
        )

        return []


# ============================================================
# NOTIFY SELLER
# ============================================================

def notify_seller(
    seller_id: str,
    notification_type: str,
    title: str,
    message: str,
    data: dict | None = None,
):
    """
    Notify a farmer or supplier who owns the product/order.
    """

    return safe_create_notification(

        user_id=seller_id,

        notification_type=
            notification_type,

        title=title,

        message=message,

        data=data,
    )


# ============================================================
# NOTIFY BUYER
# ============================================================

def notify_buyer(
    buyer_id: str,
    notification_type: str,
    title: str,
    message: str,
    data: dict | None = None,
):
    """
    Notify the buyer of an order.
    """

    return safe_create_notification(

        user_id=buyer_id,

        notification_type=
            notification_type,

        title=title,

        message=message,

        data=data,
    )
