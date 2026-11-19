"""Authenticated disease-to-supplier product matching endpoint.

This router deliberately uses the existing public products catalogue and the
existing disease_supply_recommendations rules. It does not create or mutate
any database records.
"""

from functools import lru_cache
import os
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import create_client

from auth import get_authenticated_user


router = APIRouter(
    prefix="/recommendations",
    tags=["Disease Supply Recommendations"],
)


@lru_cache(maxsize=1)
def _get_service_client():
    """Return a server-only Supabase client using the service-role key."""
    supabase_url = os.getenv("SUPABASE_URL")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not service_role_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "Disease-supply recommendations are not configured. "
                "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY on the backend."
            ),
        )

    try:
        return create_client(supabase_url, service_role_key)
    except Exception as exc:
        # Do not return configuration values or secret material to callers.
        print("Disease recommendation client initialization failed:", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="The recommendation service is temporarily unavailable.",
        ) from exc


def _normalize(value: Any) -> str:
    """Normalize case, punctuation and whitespace for deterministic matching."""
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _product_text(product: dict[str, Any]) -> str:
    fields = (
        product.get("product_name"),
        product.get("category"),
        product.get("brand"),
        product.get("description"),
        product.get("recommendation_tags"),
    )
    return _normalize(" ".join(str(value or "") for value in fields))


def _is_listed_and_in_stock(product: dict[str, Any]) -> bool:
    """Require an available listing and a stock state that is not sold out."""
    status = _normalize(product.get("status"))
    availability = _normalize(product.get("availability"))

    if status != "available":
        return False

    if availability in {
        "unavailable",
        "out of stock",
        "out_of_stock",
        "sold",
        "sold out",
        "sold_out",
        "inactive",
    }:
        return False

    if availability in {"in stock", "in_stock", "available"}:
        return True

    if "in stock" in availability or "available" in availability:
        return True

    # Some existing listings rely on quantity rather than an availability label.
    quantity = product.get("quantity")
    try:
        return quantity is not None and float(quantity) > 0
    except (TypeError, ValueError):
        return False


def _contains_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    """Match whole normalized words/phrases, not incidental substrings."""
    padded = f" {_normalize(text)} "
    return any(f" {_normalize(phrase)} " in padded for phrase in phrases)


def _matches_rule_category(
    requested_category: str,
    product: dict[str, Any],
) -> bool:
    """Conservative category matching; avoid cross-category false positives."""
    rule_category = _normalize(requested_category)
    product_category = _normalize(product.get("category"))
    product_name = _normalize(product.get("product_name"))
    brand = _normalize(product.get("brand"))
    description = _normalize(product.get("description"))
    tags = product.get("recommendation_tags") or {}

    # Product name, brand and description can evidence crop-protection type.
    # Category text is intentionally excluded from evidence: a generic
    # "Pesticides" category alone does not prove that a product is an insecticide.
    crop_protection_text = " ".join((product_name, brand, description))
    structured_tag_text = _normalize(tags if isinstance(tags, str) else str(tags))

    if rule_category in {"fungicide", "fungicides"}:
        # The catalogue stores fungicides under the broad Pesticides category.
        # Require an explicit fungicide/fungal term in the product itself.
        return (
            product_category in {"pesticides", "fungicide", "fungicides"}
            and _contains_phrase(
                crop_protection_text,
                ("fungicide", "fungicides", "fungal"),
            )
        )

    if rule_category in {"pest control", "pesticide", "pesticides", "insect control"}:
        allowed_categories = {"", "pesticides", "pest control", "insect control"}
        # Never classify a fungicide as pest control just because both are
        # stored under the generic Pesticides category.
        if _contains_phrase(crop_protection_text, ("fungicide", "fungicides", "fungal")):
            return False
        pest_evidence = _contains_phrase(
            crop_protection_text,
            (
                "insecticide",
                "insecticides",
                "insect spray",
                "insect",
                "insects",
                "armyworm",
                "caterpillar",
                "caterpillars",
                "larva",
                "larvae",
                "pest control",
            ),
        )
        return product_category in allowed_categories and pest_evidence

    if rule_category in {"sprayer", "sprayers", "spraying equipment"}:
        return (
            product_category in {"sprayer", "sprayers"}
            or _contains_phrase(product_name, ("sprayer", "sprayers", "knapsack"))
        )

    if rule_category in {
        "protective equipment",
        "personal protective equipment",
        "ppe",
        "safety equipment",
    }:
        explicit_ppe_categories = {
            "protective equipment",
            "personal protective equipment",
            "ppe",
            "safety equipment",
        }
        ppe_item_terms = (
            "glove",
            "gloves",
            "mask",
            "masks",
            "goggle",
            "goggles",
            "respirator",
            "respirators",
            "coverall",
            "coveralls",
            "safety boot",
            "safety boots",
            "gumboot",
            "gumboots",
            "protective equipment",
            "personal protective equipment",
            "ppe",
        )
        # Deliberately do not scan long scraped descriptions here: generic
        # phrases such as "safe payments" or "certified for safety" must not
        # turn an irrigation pump or tractor into protective equipment.
        return (
            product_category in explicit_ppe_categories
            or _contains_phrase(product_name, ppe_item_terms)
            or _contains_phrase(brand, ppe_item_terms)
            or _contains_phrase(structured_tag_text, ppe_item_terms)
        )

    # For future rule categories, require an exact normalized category match.
    return bool(rule_category) and product_category == rule_category


def _product_role_and_notice(rule_category: str) -> tuple[str, bool, str]:
    normalized = _normalize(rule_category)

    if normalized in {"fungicide", "fungicides", "pest control", "pesticide", "pesticides", "insect control"}:
        return (
            "crop_protection_candidate",
            True,
            (
                "Category match only. Verify the active ingredient and the "
                "product label's approved crop, target disease or pest, rate, "
                "and safety instructions before use."
            ),
        )

    if normalized in {"sprayer", "sprayers", "spraying equipment"}:
        return (
            "application_equipment",
            False,
            "Application equipment only; this product is not a disease treatment.",
        )

    if normalized in {"protective equipment", "personal protective equipment", "ppe"}:
        return (
            "protective_equipment_candidate",
            False,
            "Confirm the equipment type and protective specifications before use.",
        )

    return (
        "farm_supply_category_match",
        False,
        "This is a category match, not a guarantee of agronomic suitability.",
    )


def _load_supplier_profiles(client, supplier_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Load only the business contact fields needed for marketplace display."""
    if not supplier_ids:
        return {}

    response = (
        client.table("business_profiles")
        .select("supplier_id,business_name,phone_number,email,location,description")
        .in_("supplier_id", supplier_ids)
        .execute()
    )

    profiles: dict[str, dict[str, Any]] = {}
    for profile in response.data or []:
        supplier_id = str(profile.get("supplier_id") or "")
        if not supplier_id:
            continue
        profiles[supplier_id] = {
            "supplier_id": supplier_id,
            "business_name": profile.get("business_name"),
            "phone": profile.get("phone_number"),
            "email": profile.get("email"),
            "location": profile.get("location"),
            "description": profile.get("description"),
        }
    return profiles


@router.get("/disease-supplies")
def get_disease_supply_matches(
    crop: str = Query(..., min_length=2, max_length=80),
    disease: str = Query(..., min_length=2, max_length=120),
    _user=Depends(get_authenticated_user),
):
    """Return disease rule categories with matching, in-stock supplier items.

    Authentication is required. The service-role key is used only on this
    server-side route to read rule rows and supplier business profiles that are
    intentionally not exposed through public RLS policies.
    """
    crop_key = _normalize(crop)
    disease_key = _normalize(disease)

    if not crop_key or not disease_key:
        raise HTTPException(status_code=422, detail="Crop and disease are required.")

    client = _get_service_client()

    try:
        rules_response = (
            client.table("disease_supply_recommendations")
            .select("crop,disease,category,reason,priority")
            .eq("crop", crop_key)
            .eq("disease", disease_key)
            .order("category")
            .execute()
        )
        rules = rules_response.data or []

        if not rules:
            return {
                "crop": crop_key,
                "disease": disease_key,
                "recommendations": [],
                "message": "No configured supplier recommendation rules were found for this diagnosis.",
                "safety_note": (
                    "Do not select a pesticide solely from a diagnosis name. "
                    "Use only products whose label is appropriate for the crop and target problem."
                ),
            }

        products_response = (
            client.table("products")
            .select(
                "id,product_name,crop,description,quantity,unit,price_per_unit,"
                "region,image_url,image_urls,status,created_at,seller_id,"
                "seller_type,product_type,category,brand,availability,rating,"
                "supplier_location,recommendation_tags"
            )
            .eq("product_type", "supply")
            .eq("seller_type", "supplier")
            .eq("status", "available")
            .limit(500)
            .execute()
        )
        available_products = [
            product
            for product in (products_response.data or [])
            if _is_listed_and_in_stock(product)
        ]

        matched_by_rule: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
        matched_seller_ids: set[str] = set()

        for rule in rules:
            category = rule.get("category") or ""
            matches = [
                product
                for product in available_products
                if _matches_rule_category(category, product)
            ]
            matched_by_rule.append((rule, matches))
            for product in matches:
                seller_id = product.get("seller_id")
                if seller_id:
                    matched_seller_ids.add(str(seller_id))

        profiles_by_supplier = _load_supplier_profiles(
            client,
            sorted(matched_seller_ids),
        )

        recommendations = []
        for rule, matches in matched_by_rule:
            category = rule.get("category") or "Recommended Supplies"
            product_role, requires_label_check, product_notice = _product_role_and_notice(category)

            response_products = []
            for product in matches:
                seller_id = str(product.get("seller_id") or "")
                response_products.append(
                    {
                        "id": product.get("id"),
                        "product_name": product.get("product_name"),
                        "description": product.get("description"),
                        "category": product.get("category"),
                        "brand": product.get("brand"),
                        "quantity": product.get("quantity"),
                        "unit": product.get("unit"),
                        "price_per_unit": product.get("price_per_unit"),
                        "region": product.get("region"),
                        "image_url": product.get("image_url"),
                        "image_urls": product.get("image_urls"),
                        "availability": product.get("availability"),
                        "rating": product.get("rating"),
                        "seller_id": seller_id or None,
                        "supplier_location": (
                            product.get("supplier_location")
                            or (profiles_by_supplier.get(seller_id) or {}).get("location")
                        ),
                        "supplier": profiles_by_supplier.get(seller_id),
                        "product_role": product_role,
                        "label_verification_required": requires_label_check,
                        "recommendation_notice": product_notice,
                    }
                )

            recommendations.append(
                {
                    "category": category,
                    "priority": rule.get("priority") or "medium",
                    "reason": rule.get("reason") or "",
                    "products": response_products,
                    "product_count": len(response_products),
                    "match_status": "products_found" if response_products else "no_matching_stock",
                }
            )

        return {
            "crop": crop_key,
            "disease": disease_key,
            "recommendations": recommendations,
            "safety_note": (
                "Product category matches are not treatment approvals. For pesticides and fungicides, "
                "verify the active ingredient and product label for the crop and target disease or pest "
                "before recommending or applying the product."
            ),
        }

    except HTTPException:
        raise
    except Exception as exc:
        print("Disease-supply recommendation query failed:", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Disease-supply recommendations are temporarily unavailable.",
        ) from exc
