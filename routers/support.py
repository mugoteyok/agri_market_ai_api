
from fastapi import APIRouter, Depends, HTTPException
from database import supabase
from auth import get_authenticated_user


# ============================================================
# ROUTER
# ============================================================

router = APIRouter(
    prefix="/api/support",
    tags=["Customer Support"],
)


# ============================================================
# CONSTANTS
# ============================================================

ALLOWED_CUSTOMER_ROLES = {
    "farmer",
    "supplier",
    "agricultural_business",
}


# ============================================================
# AUTHENTICATION / USER HELPERS
# ============================================================

def get_user_id(user) -> str:
    """
    Get the authenticated Supabase user's ID.
    """

    user_id = getattr(user, "id", None)

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Authenticated user ID is missing.",
        )

    return str(user_id)


def get_user_role(user) -> str:
    """
    Get the user's role from the profiles table.

    profiles.id = auth.users.id

    This is the application's source of truth for roles.
    """

    user_id = get_user_id(user)

    try:
        response = (
            supabase
            .from_("profiles")
            .select("role")
            .eq("id", user_id)
            .maybe_single()
            .execute()
        )

        profile = response.data

    except Exception as e:
        print(
            "SUPPORT ROLE LOOKUP ERROR:",
            str(e),
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to verify user role.",
        )

    if not profile or not profile.get("role"):
        raise HTTPException(
            status_code=403,
            detail="User role is not available.",
        )

    role = str(
        profile["role"]
    ).strip().lower()

    if role not in ALLOWED_CUSTOMER_ROLES:
        raise HTTPException(
            status_code=403,
            detail=(
                "This account is not allowed "
                "to use customer support."
            ),
        )

    return role


# ============================================================
# GET SUPPORT CATEGORIES
# ============================================================

@router.get("/categories")
async def get_support_categories(
    user=Depends(get_authenticated_user),
):
    """
    Return active customer support categories.

    Available to authenticated farmers, suppliers,
    and agricultural businesses.
    """

    get_user_role(user)

    try:
        response = (
            supabase
            .from_("support_categories")
            .select(
                "id,name,description,is_active,created_at"
            )
            .eq("is_active", True)
            .order("name")
            .execute()
        )

        return {
            "success": True,
            "categories": response.data or [],
        }

    except Exception as e:
        print(
            "SUPPORT CATEGORIES ERROR:",
            str(e),
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to load support categories.",
        )


# ============================================================
# CREATE SUPPORT TICKET
# ============================================================

@router.post("/tickets")
async def create_support_ticket(
    payload: dict,
    user=Depends(get_authenticated_user),
):
    """
    Create a customer support ticket.

    The authenticated user's ID and role are always taken
    from the authenticated session / profiles table.

    The client cannot choose another user's ID or role.
    """

    user_id = get_user_id(user)
    user_role = get_user_role(user)

    subject = str(
        payload.get("subject", "")
    ).strip()

    message = str(
        payload.get("message", "")
    ).strip()

    category_id = payload.get("category_id")

    priority = str(
        payload.get("priority", "normal")
    ).strip().lower()

    channel = str(
        payload.get("channel", "app")
    ).strip().lower()

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    if not subject:
        raise HTTPException(
            status_code=400,
            detail="Support ticket subject is required.",
        )

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Support ticket message is required.",
        )

    if priority not in {
        "low",
        "normal",
        "high",
        "urgent",
    }:
        raise HTTPException(
            status_code=400,
            detail="Invalid support ticket priority.",
        )

    if channel not in {
        "app",
        "whatsapp",
        "email",
        "website",
    }:
        raise HTTPException(
            status_code=400,
            detail="Invalid support ticket channel.",
        )

    # --------------------------------------------------------
    # OPTIONAL CATEGORY VALIDATION
    # --------------------------------------------------------

    if category_id:
        try:
            category_response = (
                supabase
                .from_("support_categories")
                .select("id")
                .eq("id", category_id)
                .eq("is_active", True)
                .maybe_single()
                .execute()
            )

            if not category_response.data:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid or inactive support category.",
                )

        except HTTPException:
            raise

        except Exception as e:
            print(
                "SUPPORT CATEGORY VALIDATION ERROR:",
                str(e),
            )

            raise HTTPException(
                status_code=500,
                detail="Unable to validate support category.",
            )

    # --------------------------------------------------------
    # CREATE TICKET
    # --------------------------------------------------------

    try:
        ticket_response = (
            supabase
            .from_("support_tickets")
            .insert({
                "user_id": user_id,
                "user_role": user_role,
                "category_id": category_id,
                "subject": subject,
                "priority": priority,
                "channel": channel,
            })
            .select(
                """
                id,
                user_id,
                user_role,
                category_id,
                subject,
                status,
                priority,
                channel,
                created_at,
                updated_at,
                closed_at
                """
            )
            .single()
            .execute()
        )

        ticket = ticket_response.data

        if not ticket:
            raise HTTPException(
                status_code=500,
                detail="Unable to create support ticket.",
            )

    except HTTPException:
        raise

    except Exception as e:
        print(
            "CREATE SUPPORT TICKET ERROR:",
            str(e),
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to create support ticket.",
        )

    # --------------------------------------------------------
    # CREATE FIRST MESSAGE
    # --------------------------------------------------------

    try:
        message_response = (
            supabase
            .from_("support_messages")
            .insert({
                "ticket_id": ticket["id"],
                "sender_id": user_id,
                "sender_role": user_role,
                "message": message,
                "is_internal": False,
            })
            .select(
                """
                id,
                ticket_id,
                sender_id,
                sender_role,
                message,
                created_at,
                is_internal
                """
            )
            .single()
            .execute()
        )

        first_message = message_response.data

    except Exception as e:
        print(
            "CREATE SUPPORT MESSAGE ERROR:",
            str(e),
        )

        # ----------------------------------------------------
        # CLEAN UP TICKET IF FIRST MESSAGE FAILED
        # ----------------------------------------------------

        try:
            supabase \
                .from_("support_tickets") \
                .delete() \
                .eq("id", ticket["id"]) \
                .eq("user_id", user_id) \
                .execute()
        except Exception as cleanup_error:
            print(
                "SUPPORT TICKET CLEANUP ERROR:",
                str(cleanup_error),
            )

        raise HTTPException(
            status_code=500,
            detail="Unable to create support ticket message.",
        )

    return {
        "success": True,
        "ticket": ticket,
        "message": first_message,
    }


# ============================================================
# GET MY SUPPORT TICKETS
# ============================================================

@router.get("/tickets")
async def get_my_support_tickets(
    user=Depends(get_authenticated_user),
):
    """
    Return support tickets belonging only to the
    authenticated user.
    """

    user_id = get_user_id(user)

    get_user_role(user)

    try:
        response = (
            supabase
            .from_("support_tickets")
            .select(
                """
                id,
                user_id,
                user_role,
                category_id,
                subject,
                status,
                priority,
                channel,
                created_at,
                updated_at,
                closed_at,
                support_categories(
                    id,
                    name,
                    description
                )
                """
            )
            .eq("user_id", user_id)
            .order(
                "created_at",
                desc=True,
            )
            .execute()
        )

        return {
            "success": True,
            "tickets": response.data or [],
        }

    except Exception as e:
        print(
            "GET SUPPORT TICKETS ERROR:",
            str(e),
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to load support tickets.",
        )


# ============================================================
# GET ONE SUPPORT TICKET
# ============================================================

@router.get("/tickets/{ticket_id}")
async def get_support_ticket(
    ticket_id: str,
    user=Depends(get_authenticated_user),
):
    """
    Return one support ticket and its messages.

    A user can only access their own ticket.
    """

    user_id = get_user_id(user)

    get_user_role(user)

    # --------------------------------------------------------
    # GET TICKET
    # --------------------------------------------------------

    try:
        ticket_response = (
            supabase
            .from_("support_tickets")
            .select(
                """
                id,
                user_id,
                user_role,
                category_id,
                subject,
                status,
                priority,
                channel,
                created_at,
                updated_at,
                closed_at,
                support_categories(
                    id,
                    name,
                    description
                )
                """
            )
            .eq("id", ticket_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        ticket = ticket_response.data

    except Exception as e:
        print(
            "GET SUPPORT TICKET ERROR:",
            str(e),
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to load support ticket.",
        )

    if not ticket:
        raise HTTPException(
            status_code=404,
            detail="Support ticket not found.",
        )

    # --------------------------------------------------------
    # GET MESSAGES
    # --------------------------------------------------------

    try:
        messages_response = (
            supabase
            .from_("support_messages")
            .select(
                """
                id,
                ticket_id,
                sender_id,
                sender_role,
                message,
                created_at,
                is_internal
                """
            )
            .eq("ticket_id", ticket_id)
            .eq("is_internal", False)
            .order(
                "created_at",
                desc=False,
            )
            .execute()
        )

        messages = messages_response.data or []

    except Exception as e:
        print(
            "GET SUPPORT MESSAGES ERROR:",
            str(e),
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to load support messages.",
        )

    return {
        "success": True,
        "ticket": ticket,
        "messages": messages,
    }


# ============================================================
# ADD MESSAGE TO SUPPORT TICKET
# ============================================================

@router.post("/tickets/{ticket_id}/messages")
async def add_support_message(
    ticket_id: str,
    payload: dict,
    user=Depends(get_authenticated_user),
):
    """
    Add a customer message to an existing support ticket.

    The authenticated user must own the ticket.
    """

    user_id = get_user_id(user)
    user_role = get_user_role(user)

    message = str(
        payload.get("message", "")
    ).strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Support message is required.",
        )

    # --------------------------------------------------------
    # VERIFY TICKET OWNERSHIP
    # --------------------------------------------------------

    try:
        ticket_response = (
            supabase
            .from_("support_tickets")
            .select(
                """
                id,
                user_id,
                status
                """
            )
            .eq("id", ticket_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        ticket = ticket_response.data

    except Exception as e:
        print(
            "SUPPORT TICKET OWNERSHIP ERROR:",
            str(e),
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to verify support ticket.",
        )

    if not ticket:
        raise HTTPException(
            status_code=404,
            detail="Support ticket not found.",
        )

    # --------------------------------------------------------
    # PREVENT MESSAGES ON CLOSED TICKETS
    # --------------------------------------------------------

    if ticket.get("status") == "closed":
        raise HTTPException(
            status_code=400,
            detail="This support ticket is closed.",
        )

    # --------------------------------------------------------
    # CREATE MESSAGE
    # --------------------------------------------------------

    try:
        response = (
            supabase
            .from_("support_messages")
            .insert({
                "ticket_id": ticket_id,
                "sender_id": user_id,
                "sender_role": user_role,
                "message": message,
                "is_internal": False,
            })
            .select(
                """
                id,
                ticket_id,
                sender_id,
                sender_role,
                message,
                created_at,
                is_internal
                """
            )
            .single()
            .execute()
        )

        created_message = response.data

    except Exception as e:
        print(
            "ADD SUPPORT MESSAGE ERROR:",
            str(e),
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to add support message.",
        )

    return {
        "success": True,
        "message": created_message,
    }

