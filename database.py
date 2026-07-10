import os

from supabase import create_client, Client
from dotenv import load_dotenv


load_dotenv()


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


print("SUPABASE URL:", SUPABASE_URL)
print(
    "SUPABASE KEY EXISTS:",
    bool(SUPABASE_KEY)
)


if not SUPABASE_URL or not SUPABASE_KEY:
    raise Exception(
        "Supabase environment variables missing"
    )


supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)
