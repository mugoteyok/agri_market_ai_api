
from fastapi import HTTPException

from routers.account import get_admin_client, check_deletion_safety

TEST_USER_ID = "8dad7f2c-8924-4b80-b746-f29bb14f7289"
TEST_PRODUCT_ID = "2a137860-538d-4750-84dc-4f69f93b93f5"


def main():
    admin_client = get_admin_client()

    # Confirm the exact test product still exists.
    product = (
        admin_client.table("products")
        .select("id,farmer_id,description")
        .eq("id", TEST_PRODUCT_ID)
        .eq("farmer_id", TEST_USER_ID)
        .execute()
    )

    if not product.data:
        raise RuntimeError("Test product not found; stopping safely.")

    # Run only the safety checks. Never call delete_user().
    try:
        check_deletion_safety(admin_client, TEST_USER_ID)
    except HTTPException as exc:
        if exc.status_code == 409:
            print("PASS: Safety check returned HTTP 409.")
            print("The account deletion must be blocked.")
        else:
            print(f"Unexpected HTTP error: {exc.status_code}")
            raise
    else:
        raise RuntimeError(
            "Safety check did not block deletion. "
            "No account deletion was attempted."
        )


if __name__ == "__main__":
    main()
