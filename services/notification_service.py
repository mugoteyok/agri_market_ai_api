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
    Create one notification for one Supabase Auth user.

    IMPORTANT:
    user_id MUST be the Supabase Auth/profile UUID of the
    person who should receive the notification.
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
# SAFE CREATE NOTIFICATION
# ============================================================

def safe_create_notification(
    user_id: str,
    notification_type: str,
    title: str,
    message: str,
    data: dict | None = None,
):
    """
    Create a notification without allowing notification
    failures to break the main business operation.
    """

    try:
        if not user_id:
            print(
                "NOTIFICATION SKIPPED: missing user_id"
            )
            return []

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
    Send a notification to every farmer.

    profiles.id must correspond to the user's Supabase Auth UUID.
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
            farmer_id = farmer.get("id")

            if not farmer_id:
                continue

            result = safe_create_notification(
                user_id=farmer_id,
                notification_type=notification_type,
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
    Notify the seller of a product/order.

    seller_id MUST be the seller's Supabase Auth/profile UUID.

    This can be:
      - Farmer
      - Supplier
      - Agricultural Business
    """

    if not seller_id:
        print(
            "SELLER NOTIFICATION SKIPPED: missing seller_id"
        )
        return []

    return safe_create_notification(
        user_id=seller_id,
        notification_type=notification_type,
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

    buyer_id MUST be the buyer's Supabase Auth/profile UUID.
    """

    if not buyer_id:
        print(
            "BUYER NOTIFICATION SKIPPED: missing buyer_id"
        )
        return []

    return safe_create_notification(
        user_id=buyer_id,
        notification_type=notification_type,
        title=title,
        message=message,
        data=data,
    )
