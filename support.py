
from fastapi import APIRouter, Depends, HTTPException
from database import supabase
from auth import get_authenticated_user


router = APIRouter(
    prefix="/api/support",
    tags=["Customer Support"],
)


# ============================================================
# HELPERS
# ============================================================

ALLOWED_CUSTOMER_ROLES = {
    "farmer",
    "supplier",
    "agricultural_business",
}


def get_user_role(user) -> str:
    """
    Get the application role for the authenticated user.

    The role is expected to be stored in Supabase user metadata.
    """

    metadata = user.user_metadata or {}

    role = (
        metadata.get("role")
        or metadata.get("user_role")
        or metadata.get("account_type")
    )

    if not role:
        raise HTTPException(
            status_code=403,
            detail="User role is not available.",
        )

    role = str(role).strip().lower()

    if role not in ALLOWED_CUSTOMER_ROLES:
        raise HTTPException(
            status_code=403,
            detail="This account is not allowed to use customer support.",
        )

    return role


def get_user_id(user) -> str:
    """
    Return the authenticated Supabase user ID.
    """

    user_id = getattr(user, "id", None)

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Authenticated user ID is missing.",
        )

    return str(user_id)


# ============================================================
# GET SUPPORT CATEGORIES
# ============================================================

@router.get("/categories")
async def get_support_categories(
    user=Depends(get_authenticated_user),
):
    """
    Return active customer support categories.
    """

    # Confirm the authenticated account is an allowed
    # customer account.
    get_user_role(user)

    try:
        response = (
            supabase
            .table("support_categories")
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
            detail="Failed to load support categories.",
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
    Create a new support ticket for the authenticated user.
    """

    user_id = get_user_id(user)
    user_role = get_user_role(user)

    subject = payload.get("subject")
    category_id = payload.get("category_id")
    message = payload.get("message")

    if not subject:
        raise HTTPException(
            status_code=400,
            detail="Subject is required.",
        )

    if not str(subject).strip():
        raise HTTPException(
            status_code=400,
            detail="Subject cannot be empty.",
        )

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Message is required.",
        )

    if not str(message).strip():
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty.",
        )

    try:
        # ========================================================
        # VERIFY CATEGORY
        # ========================================================

        category = None

        if category_id:
            category_response = (
                supabase
                .table("support_categories")
                .select("id,name,is_active")
                .eq("id", category_id)
                .eq("is_active", True)
                .maybe_single()
                .execute()
            )

            category = category_response.data

            if not category:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid or inactive support category.",
                )

        # ========================================================
        # CREATE TICKET
        # ========================================================

        ticket_response = (
            supabase
            .table("support_tickets")
            .insert(
                {
                    "user_id": user_id,
                    "user_role": user_role,
                    "category_id": category_id,
                    "subject": str(subject).strip(),
                    "status": "open",
                    "priority": "normal",
                    "channel": "app",
                }
            )
            .execute()
        )

        if not ticket_response.data:
            raise HTTPException(
                status_code=500,
                detail="Failed to create support ticket.",
            )

        ticket = ticket_response.data[0]

        # ========================================================
        # CREATE FIRST MESSAGE
        # ========================================================

        message_response = (
            supabase
            .table("support_messages")
            .insert(
                {
                    "ticket_id": ticket["id"],
                    "sender_id": user_id,
                    "sender_role": user_role,
                    "message": str(message).strip(),
                    "is_internal": False,
                }
            )
            .execute()
        )

        if not message_response.data:
            raise HTTPException(
                status_code=500,
                detail="Ticket was created but the initial message failed.",
            )

        return {
            "success": True,
            "ticket": ticket,
            "message": message_response.data[0],
        }

    except HTTPException:
        raise

    except Exception as e:
        print(
            "CREATE SUPPORT TICKET ERROR:",
            str(e),
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to create support ticket.",
        )


# ============================================================
# GET MY SUPPORT TICKETS
# ============================================================

@router.get("/tickets")
async def get_my_support_tickets(
    user=Depends(get_authenticated_user),
):
    """
    Return support tickets belonging to the authenticated user.
    """

    user_id = get_user_id(user)
    get_user_role(user)

    try:
        response = (
            supabase
            .table("support_tickets")
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
                support_categories (
                    id,
                    name,
                    description
                )
                """
            )
            .eq("user_id", user_id)
            .order("created_at", desc=True)
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
            detail="Failed to load support tickets.",
        )


# ============================================================
# GET SINGLE SUPPORT TICKET
# ============================================================

@router.get("/tickets/{ticket_id}")
async def get_support_ticket(
    ticket_id: str,
    user=Depends(get_authenticated_user),
):
    """
    Return one ticket and its messages.

    Only the owner of the ticket can access it.
    """

    user_id = get_user_id(user)
    get_user_role(user)

    try:
        # ========================================================
        # LOAD TICKET
        # ========================================================

        ticket_response = (
            supabase
            .table("support_tickets")
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
                support_categories (
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

        if not ticket:
            raise HTTPException(
                status_code=404,
                detail="Support ticket not found.",
            )

        # ========================================================
        # LOAD MESSAGES
        # ========================================================

        messages_response = (
            supabase
            .table("support_messages")
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
            .order("created_at")
            .execute()
        )

        return {
            "success": True,
            "ticket": ticket,
            "messages": messages_response.data or [],
        }

    except HTTPException:
        raise

    except Exception as e:
        print(
            "GET SUPPORT TICKET ERROR:",
            str(e),
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to load support ticket.",
        )


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
    """

    user_id = get_user_id(user)
    user_role = get_user_role(user)

    message = payload.get("message")

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Message is required.",
        )

    if not str(message).strip():
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty.",
        )

    try:
        # ========================================================
        # VERIFY TICKET OWNERSHIP
        # ========================================================

        ticket_response = (
            supabase
            .table("support_tickets")
            .select(
                "id,user_id,status"
            )
            .eq("id", ticket_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        ticket = ticket_response.data

        if not ticket:
            raise HTTPException(
                status_code=404,
                detail="Support ticket not found.",
            )

        # ========================================================
        # PREVENT MESSAGES ON CLOSED TICKETS
        # ========================================================

        if ticket["status"] == "closed":
            raise HTTPException(
                status_code=400,
                detail="This support ticket is closed.",
            )

        # ========================================================
        # INSERT CUSTOMER MESSAGE
        # ========================================================

        response = (
            supabase
            .table("support_messages")
            .insert(
                {
                    "ticket_id": ticket_id,
                    "sender_id": user_id,
                    "sender_role": user_role,
                    "message": str(message).strip(),
                    "is_internal": False,
                }
            )
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=500,
                detail="Failed to send support message.",
            )

        # ========================================================
        # UPDATE TICKET
        # ========================================================

        (
            supabase
            .table("support_tickets")
            .update(
                {
                    "status": "open",
                }
            )
            .eq("id", ticket_id)
            .eq("user_id", user_id)
            .execute()
        )

        return {
            "success": True,
            "message": response.data[0],
        }

    except HTTPException:
        raise

    except Exception as e:
        print(
            "ADD SUPPORT MESSAGE ERROR:",
            str(e),
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to send support message.",
        )

