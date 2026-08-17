from database import supabase


def create_notification(
    user_id: str,
    title: str,
    message: str,
    notification_type: str,
):
    """
    Creates a notification for a Supabase Auth user.

    Notification failures are intentionally ignored so that
    marketplace operations are not rolled back because of a
    notification problem.
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

        return None
