from database import supabase


def create_notification(
    user_id: str,
    title: str,
    message: str,
    notification_type: str,
):
    """
    Create a notification for a Supabase Auth user.

    The backend uses the Supabase service-role client,
    so it can create notifications for another user.
    """

    try:
        response = (
            supabase
            .table("notifications")
            .insert({
                "user_id": user_id,
                "title": title,
                "message": message,
                "type": notification_type,
                "is_read": False,
            })
            .execute()
        )

        return response.data

    except Exception as e:

        print(
            "NOTIFICATION ERROR:",
            str(e),
        )

        # Notification failure should NOT break
        # the actual marketplace transaction.
        return None
