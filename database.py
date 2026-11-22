import os
from functools import lru_cache

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase URL or publishable key is missing.")

# Existing shared client; preserve for unrelated backend features.
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def create_user_client(access_token: str) -> Client:
    """Create an isolated client that forwards one user's JWT to PostgREST."""
    if not access_token or not access_token.strip():
        raise ValueError("A valid user access token is required.")

    client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    client.postgrest.auth(access_token.strip())
    return client


@lru_cache(maxsize=1)
def get_admin_supabase() -> Client:
    """Return the privileged backend client; never expose it to Flutter."""
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not service_key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is not configured.")
    return create_client(SUPABASE_URL, service_key)
