
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import get_authenticated_user
from database import supabase


router = APIRouter(
    prefix="/api/support/admin",
    tags=["Support Administration"],
)


# ============================================================
# SUPPORT AGENT AUTHORIZATION
# ============================================================

async def get_support_agent(
    user=Depends(get_authenticated_user),
):
    """
    Verify that the authenticated Supabase user is an active
    support agent.

    This is the security gate for all support administration
    endpoints.
    """

    user_id = getattr(user, "id", None)

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Authenticated user not found.",
        )

    try:
        response = (
            supabase
            .from_("support_agents")
            .select(
                "id,user_id,display_name,email,agent_role,is_active,created_at"
            )
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        agent = response.data

        if not agent:
            raise HTTPException(
                status_code=403,
                detail="Support administrator access required.",
            )

        if not agent.get("is_active"):
            raise HTTPException(
                status_code=403,
                detail="Support agent account is inactive.",
            )

        return agent

    except HTTPException:
        raise

    except Exception as e:
        print(
            "SUPPORT AGENT AUTHORIZATION ERROR:",
            str(e),
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to verify support agent access.",
        )


# ============================================================
# MANAGEMENT ROLE CHECK
# ============================================================

def require_management_role(agent):
    """
    Supervisors and administrators can view management data.
    """

    role = str(
        agent.get("agent_role", "")
    ).strip().lower()

    if role not in {
        "supervisor",
        "admin",
    }:
        raise HTTPException(
            status_code=403,
            detail="Supervisor or administrator access required.",
        )


# ============================================================
# ADMIN ROLE CHECK
# ============================================================

def require_admin_role(agent):
    """
    Only administrators can create or manage support staff.
    """

    role = str(
        agent.get("agent_role", "")
    ).strip().lower()

    if role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Administrator access required.",
        )


# ============================================================
# RESPONSE MODELS
# ============================================================

class TicketStatusUpdate(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None


class SupportReply(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=5000,
    )


class CreateSupportAgent(BaseModel):
    display_name: str = Field(
        ...,
        min_length=2,
        max_length=120,
    )

    email: str = Field(
        ...,
        min_length=5,
        max_length=320,
    )

    agent_role: str = Field(
        ...,
        min_length=1,
        max_length=30,
    )


# ============================================================
# CONSTANTS
# ============================================================

VALID_STATUSES = {
    "open",
    "pending",
    "resolved",
    "closed",
}

VALID_PRIORITIES = {
    "low",
    "normal",
    "high",
    "urgent",
}

VALID_AGENT_ROLES = {
    "agent",
    "supervisor",
    "admin",
}


# ============================================================
# DASHBOARD STATS
# ============================================================

@router.get("/stats")
async def get_support_stats(
    agent=Depends(get_support_agent),
):
    """
    Dashboard statistics for the support portal.
    """

    try:
        tickets_response = (
            supabase
            .from_("support_tickets")
            .select(
                "id,status,priority,created_at,updated_at"
            )
            .execute()
        )

        tickets = tickets_response.data or []

        now = datetime.now(timezone.utc)

        open_count = 0
        pending_count = 0
        resolved_count = 0
        closed_count = 0
        urgent_count = 0
        today_count = 0

        for ticket in tickets:
            status = str(
                ticket.get("status", "")
            ).lower()

            priority = str(
                ticket.get("priority", "")
            ).lower()

            if status == "open":
                open_count += 1

            elif status == "pending":
                pending_count += 1

            elif status == "resolved":
                resolved_count += 1

            elif status == "closed":
                closed_count += 1

            if priority == "urgent":
                urgent_count += 1

            created_at = ticket.get("created_at")

            if created_at:
                try:
                    created = datetime.fromisoformat(
                        created_at.replace(
                            "Z",
                            "+00:00",
                        )
                    )

                    if created.date() == now.date():
                        today_count += 1

                except Exception:
                    pass

        return {
            "total_tickets": len(tickets),
            "open_tickets": open_count,
            "pending_tickets": pending_count,
            "resolved_tickets": resolved_count,
            "closed_tickets": closed_count,
            "urgent_tickets": urgent_count,
            "new_today": today_count,
        }

    except Exception as e:
        print(
            "SUPPORT STATS ERROR:",
            str(e),
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to load support statistics.",
        )


# ============================================================
# ADMIN TICKET LIST
# ============================================================

@router.get("/tickets")
async def get_support_tickets(
    status: Optional[str] = Query(
        default=None,
    ),
    priority: Optional[str] = Query(
        default=None,
    ),
    user_role: Optional[str] = Query(
        default=None,
    ),
    category_id: Optional[str] = Query(
        default=None,
    ),
    agent=Depends(get_support_agent),
):
    """
    Return support tickets for the internal support portal.

    Unlike the customer endpoint, this endpoint can see tickets
    belonging to all customers.
    """

    if status and status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="Invalid ticket status.",
        )

    if priority and priority not in VALID_PRIORITIES:
        raise HTTPException(
            status_code=400,
            detail="Invalid ticket priority.",
        )

    valid_roles = {
        "farmer",
        "supplier",
        "agricultural_business",
    }

    if user_role and user_role not in valid_roles:
        raise HTTPException(
            status_code=400,
            detail="Invalid customer role.",
        )

    try:
        query = (
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
                    name
                )
                """
            )
            .order(
                "updated_at",
                desc=True,
            )
        )

        if status:
            query = query.eq(
                "status",
                status,
            )

        if priority:
            query = query.eq(
                "priority",
                priority,
            )

        if user_role:
            query = query.eq(
                "user_role",
                user_role,
            )

        if category_id:
            query = query.eq(
                "category_id",
                category_id,
            )

        response = query.execute()

        return {
            "tickets": response.data or [],
        }

    except Exception as e:
        print(
            "SUPPORT ADMIN TICKETS ERROR:",
            str(e),
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to load support tickets.",
        )


# ============================================================
# GET SINGLE TICKET
# ============================================================

@router.get("/tickets/{ticket_id}")
async def get_support_ticket(
    ticket_id: str,
    agent=Depends(get_support_agent),
):
    """
    Get a complete ticket and its customer-visible messages.
    """

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
            .eq(
                "id",
                ticket_id,
            )
            .maybe_single()
            .execute()
        )

        ticket = ticket_response.data

        if not ticket:
            raise HTTPException(
                status_code=404,
                detail="Support ticket not found.",
            )

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
            .eq(
                "ticket_id",
                ticket_id,
            )
            .eq(
                "is_internal",
                False,
            )
            .order(
                "created_at",
                desc=False,
            )
            .execute()
        )

        return {
            "ticket": ticket,
            "messages": messages_response.data or [],
        }

    except HTTPException:
        raise

    except Exception as e:
        print(
            "SUPPORT ADMIN TICKET ERROR:",
            str(e),
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to load support ticket.",
        )


# ============================================================
# SEND SUPPORT REPLY
# ============================================================

@router.post("/tickets/{ticket_id}/messages")
async def send_support_reply(
    ticket_id: str,
    payload: SupportReply,
    agent=Depends(get_support_agent),
):
    """
    Send a reply from a support agent.
    """

    message = payload.message.strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty.",
        )

    try:
        ticket_response = (
            supabase
            .from_("support_tickets")
            .select(
                "id,status"
            )
            .eq(
                "id",
                ticket_id,
            )
            .maybe_single()
            .execute()
        )

        ticket = ticket_response.data

        if not ticket:
            raise HTTPException(
                status_code=404,
                detail="Support ticket not found.",
            )

        if ticket.get("status") == "closed":
            raise HTTPException(
                status_code=400,
                detail="Closed tickets cannot receive new messages.",
            )

        insert_response = (
            supabase
            .from_("support_messages")
            .insert({
                "ticket_id": ticket_id,
                "sender_id": agent["user_id"],
                "sender_role": "support",
                "message": message,
                "is_internal": False,
            })
            .execute()
        )

        inserted_messages = (
            insert_response.data or []
        )

        inserted_message = (
            inserted_messages[0]
            if inserted_messages
            else None
        )

        if not inserted_message:
            raise HTTPException(
                status_code=500,
                detail="Support message was not created.",
            )

        return {
            "message": inserted_message,
        }

    except HTTPException:
        raise

    except Exception as e:
        print(
            "SUPPORT REPLY ERROR:",
            str(e),
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to send support reply.",
        )


# ============================================================
# UPDATE TICKET
# ============================================================

@router.patch("/tickets/{ticket_id}")
async def update_support_ticket(
    ticket_id: str,
    payload: TicketStatusUpdate,
    agent=Depends(get_support_agent),
):
    """
    Update ticket status and/or priority.
    """

    if payload.status is None and payload.priority is None:
        raise HTTPException(
            status_code=400,
            detail="No ticket changes supplied.",
        )

    if (
        payload.status is not None
        and payload.status not in VALID_STATUSES
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid ticket status.",
        )

    if (
        payload.priority is not None
        and payload.priority not in VALID_PRIORITIES
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid ticket priority.",
        )

    updates = {}

    if payload.status is not None:
        updates["status"] = payload.status

        if payload.status in {
            "resolved",
            "closed",
        }:
            updates["closed_at"] = datetime.now(
                timezone.utc
            ).isoformat()

        else:
            updates["closed_at"] = None

    if payload.priority is not None:
        updates["priority"] = payload.priority

    try:
        existing_response = (
            supabase
            .from_("support_tickets")
            .select("id")
            .eq(
                "id",
                ticket_id,
            )
            .maybe_single()
            .execute()
        )

        if not existing_response.data:
            raise HTTPException(
                status_code=404,
                detail="Support ticket not found.",
            )

        response = (
            supabase
            .from_("support_tickets")
            .update(updates)
            .eq(
                "id",
                ticket_id,
            )
            .execute()
        )

        updated_tickets = (
            response.data or []
        )

        updated_ticket = (
            updated_tickets[0]
            if updated_tickets
            else None
        )

        if not updated_ticket:
            raise HTTPException(
                status_code=500,
                detail="Ticket update was not completed.",
            )

        return {
            "ticket": updated_ticket,
        }

    except HTTPException:
        raise

    except Exception as e:
        print(
            "SUPPORT TICKET UPDATE ERROR:",
            str(e),
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to update support ticket.",
        )


# ============================================================
# SUPPORT AGENTS
# ============================================================

@router.get("/agents")
async def get_support_agents(
    agent=Depends(get_support_agent),
):
    """
    List active and inactive support agents.

    Only supervisors and administrators can view the
    internal agent list.
    """

    require_management_role(agent)

    try:
        response = (
            supabase
            .from_("support_agents")
            .select(
                "id,user_id,display_name,email,agent_role,is_active,created_at"
            )
            .order(
                "created_at",
                desc=False,
            )
            .execute()
        )

        return {
            "agents": response.data or [],
        }

    except HTTPException:
        raise

    except Exception as e:
        print(
            "SUPPORT AGENTS ERROR:",
            str(e),
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to load support agents.",
        )


# ============================================================
# CREATE SUPPORT STAFF
# ============================================================

@router.post("/agents")
async def create_support_agent(
    payload: CreateSupportAgent,
    agent=Depends(get_support_agent),
):
    require_admin_role(agent)

    display_name = payload.display_name.strip()
    email = payload.email.strip().lower()
    agent_role = payload.agent_role.strip().lower()

    if not display_name:
        raise HTTPException(
            status_code=400,
            detail="Staff name cannot be empty.",
        )

    if not email:
        raise HTTPException(
            status_code=400,
            detail="Staff email cannot be empty.",
        )

    if agent_role not in VALID_AGENT_ROLES:
        raise HTTPException(
            status_code=400,
            detail="Invalid support staff role.",
        )

    try:
        # =====================================================
        # CHECK FOR EXISTING SUPPORT AGENT
        # =====================================================

        existing_response = (
            supabase
            .from_("support_agents")
            .select("id,user_id,email,is_active")
            .eq("email", email)
            .execute()
        )

        existing_agents = (
            existing_response.data
            if existing_response
            else []
        )

        if existing_agents:
            raise HTTPException(
                status_code=409,
                detail=(
                    "A support staff account with this "
                    "email already exists."
                ),
            )

        # =====================================================
        # SEND SUPABASE AUTH INVITATION
        # =====================================================

        try:
            invite_response = (
                supabase.auth.admin.invite_user_by_email(
                    email
                )
            )
        except Exception as e:
            print(
                "SUPPORT STAFF INVITATION ERROR:",
                str(e),
            )

            raise HTTPException(
                status_code=500,
                detail=(
                    "Unable to send the staff invitation. "
                    "Please check the backend Supabase "
                    "configuration."
                ),
            )

        invited_user = getattr(
            invite_response,
            "user",
            None,
        )

        if not invited_user:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Supabase did not return the invited "
                    "staff user."
                ),
            )

        invited_user_id = getattr(
            invited_user,
            "id",
            None,
        )

        if not invited_user_id:
            raise HTTPException(
                status_code=500,
                detail=(
                    "The invited staff user's ID "
                    "was not returned."
                ),
            )

        print(
            "SUPPORT STAFF INVITED:",
            invited_user_id,
            email,
        )

        # =====================================================
        # CREATE SUPPORT AGENT RECORD
        # =====================================================

        support_agent_response = (
            supabase
            .from_("support_agents")
            .insert(
                {
                    "user_id": invited_user_id,
                    "display_name": display_name,
                    "email": email,
                    "agent_role": agent_role,
                    "is_active": True,
                }
            )
            .execute()
        )

        if not support_agent_response:
            raise HTTPException(
                status_code=500,
                detail=(
                    "The support-agent database "
                    "operation returned no response."
                ),
            )

        created_agents = (
            support_agent_response.data
            or []
        )

        if not created_agents:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Staff invitation was sent, but "
                    "the support-agent record could "
                    "not be created."
                ),
            )

        created_agent = created_agents[0]

        print(
            "SUPPORT AGENT CREATED:",
            created_agent,
        )

        return {
            "message": (
                "Staff invitation sent successfully."
            ),
            "agent": created_agent,
        }

    except HTTPException:
        raise

    except Exception as e:
        print(
            "CREATE SUPPORT AGENT ERROR:",
            str(e),
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to create support staff account."
            ),
        )


# ============================================================
# SUPPORT CUSTOMERS
# ============================================================

@router.get("/customers")
async def get_support_customers(
    role: Optional[str] = Query(
        default=None,
    ),
    agent=Depends(get_support_agent),
):
    """
    Return customer profiles for the internal support portal.

    Customers are farmers, suppliers, and agricultural
    businesses. Support ticket activity is summarized for
    each customer.
    """

    valid_roles = {
        "farmer",
        "supplier",
        "agricultural_business",
    }

    if role and role not in valid_roles:
        raise HTTPException(
            status_code=400,
            detail="Invalid customer role.",
        )

    try:
        profiles_query = (
            supabase
            .from_("profiles")
            .select(
                """
                id,
                name,
                email,
                region,
                farm_size,
                created_at,
                role,
                avatar_url
                """
            )
            .order(
                "created_at",
                desc=True,
            )
        )

        if role:
            profiles_query = profiles_query.eq(
                "role",
                role,
            )

        profiles_response = (
            profiles_query.execute()
        )

        profiles = (
            profiles_response.data or []
        )

        tickets_response = (
            supabase
            .from_("support_tickets")
            .select(
                """
                id,
                user_id,
                status,
                priority,
                created_at,
                updated_at
                """
            )
            .execute()
        )

        tickets = (
            tickets_response.data or []
        )

        customer_activity = {}

        for ticket in tickets:
            user_id = ticket.get(
                "user_id"
            )

            if not user_id:
                continue

            if user_id not in customer_activity:
                customer_activity[user_id] = {
                    "ticket_count": 0,
                    "open_tickets": 0,
                    "pending_tickets": 0,
                    "urgent_tickets": 0,
                    "last_activity": None,
                }

            activity = customer_activity[
                user_id
            ]

            activity[
                "ticket_count"
            ] += 1

            status = str(
                ticket.get(
                    "status",
                    "",
                )
            ).lower()

            priority = str(
                ticket.get(
                    "priority",
                    "",
                )
            ).lower()

            if status == "open":
                activity[
                    "open_tickets"
                ] += 1

            if status == "pending":
                activity[
                    "pending_tickets"
                ] += 1

            if priority == "urgent":
                activity[
                    "urgent_tickets"
                ] += 1

            updated_at = ticket.get(
                "updated_at"
            )

            current_last = activity[
                "last_activity"
            ]

            if (
                updated_at
                and (
                    current_last is None
                    or updated_at > current_last
                )
            ):
                activity[
                    "last_activity"
                ] = updated_at

        customers = []

        for profile in profiles:
            customer_id = profile.get(
                "id"
            )

            activity = customer_activity.get(
                customer_id,
                {
                    "ticket_count": 0,
                    "open_tickets": 0,
                    "pending_tickets": 0,
                    "urgent_tickets": 0,
                    "last_activity": None,
                },
            )

            customers.append({
                "id": customer_id,
                "name": profile.get(
                    "name"
                ),
                "email": profile.get(
                    "email"
                ),
                "region": profile.get(
                    "region"
                ),
                "farm_size": profile.get(
                    "farm_size"
                ),
                "created_at": profile.get(
                    "created_at"
                ),
                "role": profile.get(
                    "role"
                ),
                "avatar_url": profile.get(
                    "avatar_url"
                ),
                "ticket_count": activity[
                    "ticket_count"
                ],
                "open_tickets": activity[
                    "open_tickets"
                ],
                "pending_tickets": activity[
                    "pending_tickets"
                ],
                "urgent_tickets": activity[
                    "urgent_tickets"
                ],
                "last_activity": activity[
                    "last_activity"
                ],
            })

        return {
            "customers": customers,
        }

    except HTTPException:
        raise

    except Exception as e:
        print(
            "SUPPORT CUSTOMERS ERROR:",
            str(e),
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to load support customers.",
        )

