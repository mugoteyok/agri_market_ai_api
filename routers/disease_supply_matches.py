"""Authenticated, tag-driven disease-to-supplier product recommendations."""
from functools import lru_cache
import os
import re
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import create_client
from auth import get_authenticated_user

router = APIRouter(prefix="/recommendations", tags=["Disease Supply Recommendations"])
MAX_TREATMENTS = 3
MAX_TOOLS = 2
MAX_PREVENTION = 2
MAX_NUTRITION = 2
SAFETY_NOTE = (
    "Recommendations are catalogue matches, not treatment approvals. "
    "For pesticides and fungicides, verify the active ingredient and the "
    "product label's approved crop, target disease or pest, application rate, "
    "pre-harvest interval and safety instructions before use. Follow local "
    "agricultural guidance."
)
KNOWN_PATHOGENS = {
    "coffee leaf rust": {"fungal"},
    "fall armyworm": {"insect"},
    "late blight": {"oomycete"},
}
KNOWN_PESTS = {"fall armyworm"}
PATHOGEN_ALIASES = {
    "fungus": "fungal",
    "fungi": "fungal",
    "fungal pathogen": "fungal",
    "fungal disease": "fungal",
    "insect pest": "insect",
    "insects": "insect",
    "insect": "insect",
    "oomycetes": "oomycete",
    "water mold": "oomycete",
    "water mould": "oomycete",
}

@lru_cache(maxsize=1)
def _get_service_client():
    """Return a server-only Supabase client."""
    supabase_url = os.getenv("SUPABASE_URL")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not service_role_key:
        raise HTTPException(status_code=503, detail="Disease-supply recommendations are not configured.")
    try:
        return create_client(supabase_url, service_role_key)
    except Exception as exc:
        print("Disease recommendation client initialization failed:", type(exc).__name__)
        raise HTTPException(status_code=503, detail="The recommendation service is temporarily unavailable.") from exc

def _normalize(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def _tag_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        values = value
    elif isinstance(value, str):
        values = re.split(r"[,;\n]", value)
    else:
        return []
    return list({_normalize(item) for item in values if _normalize(item)})

def _get_tags(product: dict[str, Any]) -> dict[str, Any]:
    tags = product.get("recommendation_tags")
    return tags if isinstance(tags, dict) else {}

def _tag_role(tags: dict[str, Any]) -> str:
    return _normalize(tags.get("category"))

def _tag_pathogens(tags: dict[str, Any]) -> set[str]:
    return {PATHOGEN_ALIASES.get(value, value) for value in _tag_list(tags.get("pathogens"))}

def _is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _normalize(value) in {"true", "yes", "1", "on"}

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def _is_listed_and_in_stock(product: dict[str, Any]) -> bool:
    if _normalize(product.get("status")) != "available":
        return False
    if _safe_float(product.get("quantity")) <= 0:
        return False
    availability = _normalize(product.get("availability"))
    return availability not in {
        "unavailable", "out of stock", "sold", "sold out", "inactive", "expired"
    }

def _crop_matches(tags: dict[str, Any], crop_key: str, *, universal: bool = False) -> bool:
    crops = _tag_list(tags.get("crop_types"))
    if not crops:
        return universal
    return crop_key in crops

def _pathogens_for_diagnosis(disease_key: str, rules: list[dict[str, Any]]) -> set[str]:
    known = KNOWN_PATHOGENS.get(disease_key)
    if known:
        return set(known)
    inferred = set()
    for rule in rules:
        category = _normalize(rule.get("category"))
        if category in {"fungicide", "fungicides"}:
            inferred.add("fungal")
        elif category in {"pest control", "insect control"}:
            inferred.add("insect")
    return inferred

def _product_target_match(
    tags: dict[str, Any],
    target_key: str,
    target_pathogens: set[str],
    *,
    require_exact_pest: bool = False,
) -> str | None:
    """Match a specific disease or pest; generic insect tags never identify a pest."""
    if target_key in set(_tag_list(tags.get("treats_pests"))):
        return "exact_pest"
    if require_exact_pest:
        return None
    if target_key in set(_tag_list(tags.get("treats_diseases"))):
        return "exact_disease"
    if target_pathogens & _tag_pathogens(tags):
        return "pathogen"
    return None

def _is_treatment_rule(category: str) -> bool:
    return _normalize(category) in {
        "fungicide", "fungicides", "pest control", "pesticide", "pesticides", "insect control"
    }

def _is_ppe_rule(category: str) -> bool:
    return _normalize(category) in {
        "protective equipment", "personal protective equipment", "ppe", "safety equipment"
    }

def _is_sprayer_rule(category: str) -> bool:
    return _normalize(category) in {"sprayer", "sprayers", "spraying equipment"}

def _is_healthy_label(value: str) -> bool:
    label = _normalize(value)
    if re.search(r"\b(unhealthy|not healthy|not disease free)\b", label):
        return False
    return label in {
        "healthy", "healthy crop", "healthy leaf", "no disease",
        "no disease detected", "no disease found", "disease free",
        "normal", "no issues detected"
    }

def _is_uncertain_label(value: str) -> bool:
    label = _normalize(value)
    unknown = {
        "unknown", "uncertain", "inconclusive", "unclassified", "undetermined",
        "pending", "processing", "insufficient data", "unable to determine",
        "unable to identify", "not available", "n a", "no diagnosis", "error", "failed"
    }
    return label in unknown or bool(
        re.search(r"\b(unknown|uncertain|inconclusive|unclassified|undetermined)\b", label)
    )

def _diagnosis_mode(status: str, disease: str) -> str:
    status_key = _normalize(status)
    if status_key in {"healthy", "normal"} or _is_healthy_label(disease):
        return "healthy"
    if status_key in {
        "uncertain", "unknown", "inconclusive", "unclassified",
        "undetermined", "pending", "error", "failed"
    } or _is_uncertain_label(disease):
        return "uncertain"
    return "disease"

def _ranked(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            item["_score"],
            _safe_float(item["_product"].get("rating")),
            str(item["_product"].get("created_at") or ""),
        ),
        reverse=True,
    )

def _load_supplier_profiles(client, supplier_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not supplier_ids:
        return {}
    response = (
        client.table("business_profiles")
        .select("supplier_id,business_name,phone_number,email,location,description")
        .in_("supplier_id", supplier_ids)
        .execute()
    )
    profiles = {}
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

def _make_match(product: dict[str, Any], score: int, reason: str, section: str) -> dict[str, Any]:
    return {
        "_product": product,
        "_score": score,
        "_reason": reason,
        "_section": section,
    }

def _serialize_product(match: dict[str, Any], profiles_by_supplier: dict[str, dict[str, Any]]) -> dict[str, Any]:
    product = match["_product"]
    tags = _get_tags(product)
    supplier_id = str(product.get("seller_id") or "")
    profile = profiles_by_supplier.get(supplier_id)
    section = match["_section"]
    if section in {"treatment", "prevention"}:
        role = "crop_protection_candidate" if section == "treatment" else "crop_prevention_candidate"
        label_required = True
        notice = (
            "Supplier tags indicate a possible crop-protection match. "
            "Verify the active ingredient and full product label for the "
            "specific crop and target problem before use."
        )
    elif section == "tools":
        tool_type = _normalize(tags.get("tool_type"))
        if tool_type in {"sprayer", "sprayers"}:
            role = "application_equipment"
            notice = "Application equipment only; this product is not a disease treatment."
        else:
            role = "protective_equipment_candidate"
            notice = "Confirm the equipment type and protective specifications before use."
        label_required = False
    else:
        role = "crop_nutrition_candidate"
        label_required = False
        notice = "Check the product instructions and crop-specific nutrient requirements before application."
    return {
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
        "seller_id": supplier_id or None,
        "seller_type": product.get("seller_type"),
        "product_type": product.get("product_type"),
        "status": product.get("status"),
        "supplier_location": product.get("supplier_location") or (profile or {}).get("location"),
        "supplier": profile,
        "product_role": role,
        "label_verification_required": label_required,
        "recommendation_notice": notice,
        "recommendation_score": match["_score"],
        "match_reason": match["_reason"],
        "active_ingredient": tags.get("active_ingredient"),
    }

def _make_group(
    category: str,
    section: str,
    reason: str,
    priority: str,
    matches: list[dict[str, Any]],
    profiles: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    products = [_serialize_product(match, profiles) for match in matches]
    return {
        "category": category,
        "section": section,
        "priority": priority,
        "reason": reason,
        "products": products,
        "product_count": len(products),
        "match_status": "products_found" if products else "no_matching_stock",
    }

@router.get("/disease-supplies")
def get_disease_supply_matches(
    crop: str = Query(..., min_length=2, max_length=80),
    disease: str = Query(..., min_length=2, max_length=120),
    diagnosis_status: str = Query("disease", min_length=2, max_length=30),
    _user=Depends(get_authenticated_user),
):
    """Return strictly crop-matched, tag-driven supplier recommendations."""
    crop_key = _normalize(crop)
    disease_key = _normalize(disease)
    mode = _diagnosis_mode(diagnosis_status, disease_key)
    if not crop_key:
        raise HTTPException(status_code=422, detail="Crop is required.")
    if mode == "uncertain":
        return {
            "crop": crop_key,
            "disease": disease_key,
            "diagnosis_mode": "uncertain",
            "recommendations": [],
            "message": (
                "The diagnosis is uncertain. Disease-specific crop-protection "
                "products have not been recommended."
            ),
            "safety_note": SAFETY_NOTE,
        }
    client = _get_service_client()
    try:
        rules = []
        if mode == "disease":
            rules_response = (
                client.table("disease_supply_recommendations")
                .select("crop,disease,category,reason,priority")
                .eq("crop", crop_key)
                .eq("disease", disease_key)
                .order("category")
                .execute()
            )
            rules = rules_response.data or []
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
        products = [
            product for product in (products_response.data or [])
            if _is_listed_and_in_stock(product)
            and isinstance(product.get("recommendation_tags"), dict)
            and bool(product.get("recommendation_tags"))
        ]
        treatment_matches = []
        prevention_matches = []
        nutrition_matches = []
        tool_matches = []
        target_pathogens = _pathogens_for_diagnosis(disease_key, rules)

        if mode == "healthy":
            for product in products:
                tags = _get_tags(product)
                if _tag_role(tags) == "nutrition" and _crop_matches(tags, crop_key):
                    nutrition_matches.append(
                        _make_match(product, 1, "Crop-specific nutrition product.", "nutrition")
                    )
            nutrition_matches = _ranked(nutrition_matches)[:MAX_NUTRITION]
            supplier_ids = sorted({
                str(match["_product"].get("seller_id") or "")
                for match in nutrition_matches if match["_product"].get("seller_id")
            })
            profiles = _load_supplier_profiles(client, supplier_ids)
            groups = []
            if nutrition_matches:
                groups.append(_make_group(
                    "Nutrition", "nutrition",
                    "Crop nutrition products for the identified crop. Follow the product instructions and soil or agronomy advice.",
                    "medium", nutrition_matches, profiles,
                ))
            return {
                "crop": crop_key,
                "disease": disease_key,
                "diagnosis_mode": "healthy",
                "recommendations": groups,
                "message": (
                    "Only crop-matched nutrition products are shown."
                    if groups else
                    "No tagged, in-stock nutrition products were found for this crop."
                ),
                "safety_note": SAFETY_NOTE,
            }

        rule_categories = [str(rule.get("category") or "") for rule in rules]
        requires_exact_pest = (
            disease_key in KNOWN_PESTS
            or any(
                _normalize(category) in {"pest control", "insect control"}
                for category in rule_categories
            )
        )
        has_treatment_rule = any(_is_treatment_rule(category) for category in rule_categories)
        has_ppe_rule = any(_is_ppe_rule(category) for category in rule_categories)
        has_sprayer_rule = any(_is_sprayer_rule(category) for category in rule_categories)

        if has_treatment_rule:
            for product in products:
                tags = _get_tags(product)
                if _tag_role(tags) != "treatment" or not _crop_matches(tags, crop_key):
                    continue
                if not str(tags.get("active_ingredient") or "").strip():
                    continue
                target_match = _product_target_match(
                    tags, disease_key, target_pathogens,
                    require_exact_pest=requires_exact_pest,
                )
                if target_match == "exact_pest":
                    treatment_matches.append(_make_match(
                        product, 10, "Exact crop and pest tag match.", "treatment"
                    ))
                elif target_match == "exact_disease":
                    treatment_matches.append(_make_match(
                        product, 10, "Exact crop and disease tag match.", "treatment"
                    ))
                elif target_match == "pathogen":
                    treatment_matches.append(_make_match(
                        product, 6,
                        "Same crop and pathogen type; verify the target-specific label.",
                        "treatment",
                    ))
        treatment_matches = _ranked(treatment_matches)[:MAX_TREATMENTS]

        for product in products:
            tags = _get_tags(product)
            if _tag_role(tags) != "preventive" or not _crop_matches(tags, crop_key):
                continue
            if not str(tags.get("active_ingredient") or "").strip():
                continue
            target_match = _product_target_match(
                tags, disease_key, target_pathogens,
                require_exact_pest=requires_exact_pest,
            )
            if target_match == "exact_pest":
                prevention_matches.append(_make_match(
                    product, 4,
                    "Preventive product tagged for this crop and target pest.",
                    "prevention",
                ))
            elif target_match == "exact_disease":
                prevention_matches.append(_make_match(
                    product, 4,
                    "Preventive product tagged for this crop and diagnosis.",
                    "prevention",
                ))
            elif target_match == "pathogen":
                prevention_matches.append(_make_match(
                    product, 2,
                    "Preventive product tagged for the same crop and pathogen type.",
                    "prevention",
                ))
        prevention_matches = _ranked(prevention_matches)[:MAX_PREVENTION]

        for product in products:
            tags = _get_tags(product)
            if _tag_role(tags) == "nutrition" and _crop_matches(tags, crop_key):
                nutrition_matches.append(_make_match(
                    product, 1, "Crop-specific nutrition product.", "nutrition"
                ))
        nutrition_matches = _ranked(nutrition_matches)[:MAX_NUTRITION]

        if has_ppe_rule and (treatment_matches or prevention_matches):
            for product in products:
                tags = _get_tags(product)
                tool_type = _normalize(tags.get("tool_type"))
                if _tag_role(tags) != "tool" or tool_type not in {
                    "protective equipment", "protective_equipment", "ppe"
                }:
                    continue
                if _crop_matches(tags, crop_key, universal=True):
                    tool_matches.append(_make_match(
                        product, 3,
                        "Protective equipment supporting safe product handling.",
                        "tools",
                    ))
        if has_sprayer_rule and any(_is_true(_get_tags(match["_product"]).get("spray_based")) for match in treatment_matches + prevention_matches):
            for product in products:
                tags = _get_tags(product)
                if _tag_role(tags) != "tool":
                    continue
                if _normalize(tags.get("tool_type")) not in {"sprayer", "sprayers"}:
                    continue
                if _crop_matches(tags, crop_key, universal=True):
                    tool_matches.append(_make_match(
                        product, 2,
                        "Spraying equipment for a recommended spray-based treatment.",
                        "tools",
                    ))
        tool_matches.sort(
            key=lambda match: (
                1 if _normalize(_get_tags(match["_product"]).get("tool_type"))
                in {"protective equipment", "protective_equipment", "ppe"} else 0,
                match["_score"],
                _safe_float(match["_product"].get("rating")),
            ),
            reverse=True,
        )
        tool_matches = tool_matches[:MAX_TOOLS]

        selected = treatment_matches + tool_matches + prevention_matches + nutrition_matches
        supplier_ids = sorted({
            str(match["_product"].get("seller_id") or "")
            for match in selected if match["_product"].get("seller_id")
        })
        profiles = _load_supplier_profiles(client, supplier_ids)
        groups = []
        if treatment_matches:
            groups.append(_make_group(
                "Treatment", "treatment",
                "Products tagged for this crop and disease, ranked by exact disease match before same-pathogen matches.",
                "high", treatment_matches, profiles,
            ))
        if tool_matches:
            groups.append(_make_group(
                "Tools & Safety", "tools",
                "Supporting application equipment and protective equipment. These products are not crop treatments.",
                "medium", tool_matches, profiles,
            ))
        if prevention_matches:
            groups.append(_make_group(
                "Prevention", "prevention",
                "Products tagged for preventive use on this crop and target problem.",
                "medium", prevention_matches, profiles,
            ))
        if nutrition_matches:
            groups.append(_make_group(
                "Nutrition", "nutrition",
                "Crop-specific nutrition products that may support crop management.",
                "low", nutrition_matches, profiles,
            ))
        return {
            "crop": crop_key,
            "disease": disease_key,
            "diagnosis_mode": "disease",
            "recommendations": groups,
            "message": (
                "Recommendations are ranked using structured supplier tags."
                if groups else
                "No tagged, in-stock products matched this crop and diagnosis. Untagged products are excluded."
            ),
            "safety_note": SAFETY_NOTE,
        }
    except HTTPException:
        raise
    except Exception as exc:
        print("Disease-supply recommendation query failed:", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Disease-supply recommendations are temporarily unavailable.",
        ) from exc