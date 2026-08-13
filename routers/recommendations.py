from fastapi import APIRouter, HTTPException, Query
from supabase import create_client

import os
import re


# ============================================================
# ROUTER
# ============================================================

router = APIRouter(
    prefix="/recommendations",
    tags=["Marketplace Recommendations"],
)


# ============================================================
# SUPABASE
# ============================================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "SUPABASE_URL and SUPABASE_KEY environment variables are required."
    )


supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY,
)


# ============================================================
# CATEGORY NORMALIZATION
# ============================================================

def normalize_category(value: str) -> str:

    if not value:
        return ""

    value = value.strip().lower()

    category_aliases = {

        # ----------------------------------------------------
        # FUNGICIDES
        # ----------------------------------------------------

        "fungicide": "fungicides",
        "fungicides": "fungicides",
        "fungal control": "fungicides",
        "fungal disease control": "fungicides",

        # ----------------------------------------------------
        # SPRAYERS
        # ----------------------------------------------------

        "sprayer": "sprayers",
        "sprayers": "sprayers",
        "spraying equipment": "sprayers",

        # ----------------------------------------------------
        # SEEDS
        # ----------------------------------------------------

        "seed": "seeds",
        "seeds": "seeds",

        # ----------------------------------------------------
        # TOOLS
        # ----------------------------------------------------

        "tool": "tools",
        "tools": "tools",

        # ----------------------------------------------------
        # EQUIPMENT
        # ----------------------------------------------------

        "equipment": "equipment",

        # ----------------------------------------------------
        # OTHER
        # ----------------------------------------------------

        "protective equipment":
            "protective equipment",

        "irrigation":
            "irrigation",

        "storage":
            "storage",

        "soil product":
            "soil products",

        "soil products":
            "soil products",
    }

    return category_aliases.get(
        value,
        value,
    )


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(value) -> str:

    if value is None:
        return ""

    value = str(value).lower()

    value = re.sub(
        r"[^a-z0-9\s-]",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


# ============================================================
# AGRICULTURAL KEYWORD GROUPS
# ============================================================

KEYWORD_GROUPS = {

    # ========================================================
    # FUNGAL DISEASES
    # ========================================================

    "fungicide": [
        "fungicide",
        "fungicides",
        "fungal",
        "fungus",
        "fungi",
        "fungal disease",
        "fungal infection",
        "disease control",
        "crop protection",
        "copper",
        "copper oxychloride",
        "copper fungicide",
        "systemic fungicide",
        "triazole",
        "epoxiconazole",
        "cyproconazole",
    ],


    # ========================================================
    # PEST / INSECT CONTROL
    # ========================================================

    "insecticide": [
        "insecticide",
        "insecticides",
        "pesticide",
        "pesticides",
        "insect",
        "insects",
        "pest",
        "pests",
        "pest control",
        "insect control",
        "crop protection",
    ],


    # ========================================================
    # SPRAY APPLICATION
    # ========================================================

    "sprayer": [
        "sprayer",
        "sprayers",
        "spray",
        "spraying",
        "knapsack sprayer",
        "manual sprayer",
        "application",
        "apply",
        "applying",
    ],


    # ========================================================
    # FERTILIZER / PLANT NUTRITION
    # ========================================================

    "fertilizer": [
        "fertilizer",
        "fertilisers",
        "fertiliser",
        "nutrient",
        "nutrition",
        "plant nutrition",
        "soil nutrition",
        "npk",
        "nitrogen",
        "phosphorus",
        "potassium",
    ],


    # ========================================================
    # SEEDS
    # ========================================================

    "seeds": [
        "seed",
        "seeds",
        "planting material",
        "variety",
        "resistant variety",
        "disease resistant",
    ],


    # ========================================================
    # PROTECTIVE EQUIPMENT
    # ========================================================

    "protective equipment": [
        "protective equipment",
        "protection",
        "gloves",
        "mask",
        "boots",
        "goggles",
        "ppe",
        "safety equipment",
    ],


    # ========================================================
    # IRRIGATION
    # ========================================================

    "irrigation": [
        "irrigation",
        "water",
        "watering",
        "drip irrigation",
        "irrigate",
    ],
}


# ============================================================
# STOP WORDS
# ============================================================

STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "when",
    "where",
    "using",
    "use",
    "should",
    "plant",
    "plants",
    "crop",
    "crops",
    "disease",
    "diseases",
    "recommended",
    "recommend",
    "proper",
    "regular",
    "ensure",
    "improve",
    "reduce",
    "remove",
    "maintain",
    "help",
    "may",
    "can",
    "such",
    "like",
    "other",
}


# ============================================================
# EXTRACT DIAGNOSIS KEYWORDS
# ============================================================

def extract_diagnosis_keywords(
    disease: str,
    causes: str,
    treatment: str,
    prevention: str,
):

    # --------------------------------------------------------
    # COMBINE ALL DIAGNOSIS INFORMATION
    # --------------------------------------------------------

    combined_text = " ".join([
        disease or "",
        causes or "",
        treatment or "",
        prevention or "",
    ])

    normalized = normalize_text(
        combined_text
    )

    keywords = set()


    # --------------------------------------------------------
    # DIRECT WORDS
    # --------------------------------------------------------

    words = normalized.split()

    for word in words:

        if len(word) < 4:
            continue

        if word in STOP_WORDS:
            continue

        keywords.add(
            word
        )


    # --------------------------------------------------------
    # AGRICULTURAL KEYWORD EXPANSION
    # --------------------------------------------------------

    for main_keyword, related_terms in (
        KEYWORD_GROUPS.items()
    ):

        matched = False

        for term in related_terms:

            normalized_term = normalize_text(
                term
            )

            if normalized_term in normalized:
                matched = True
                break

        if matched:

            keywords.add(
                main_keyword
            )

            for term in related_terms:

                normalized_term = normalize_text(
                    term
                )

                if normalized_term:
                    keywords.add(
                        normalized_term
                    )


    return keywords


# ============================================================
# CHECK PRODUCT AVAILABILITY
# ============================================================

def is_product_available(product: dict) -> bool:

    product_status = normalize_text(
        product.get("status", "")
    )

    availability = normalize_text(
        product.get("availability", "")
    )

    quantity = product.get(
        "quantity",
        0,
    )


    # --------------------------------------------------------
    # STATUS CHECK
    # --------------------------------------------------------

    unavailable_statuses = {
        "inactive",
        "unavailable",
        "out of stock",
        "out_of_stock",
        "sold out",
        "sold_out",
    }

    if product_status in unavailable_statuses:
        return False


    # --------------------------------------------------------
    # AVAILABILITY TEXT CHECK
    # --------------------------------------------------------

    if availability in {
        "out of stock",
        "out_of_stock",
        "unavailable",
        "sold out",
        "sold_out",
    }:
        return False


    # --------------------------------------------------------
    # QUANTITY CHECK
    # --------------------------------------------------------

    try:

        quantity_value = float(
            quantity or 0
        )

        if quantity_value <= 0:
            return False

    except Exception:

        # If quantity cannot be converted,
        # do not reject the product immediately.
        pass


    # --------------------------------------------------------
    # HANDLE VALUES LIKE:
    #
    # "17 pieces available"
    # "20 available"
    # "in stock"
    # "available"
    # --------------------------------------------------------

    if availability:

        if (
            "available" in availability
            or "in stock" in availability
            or "in_stock" in availability
        ):
            return True

        numbers = re.findall(
            r"\d+(?:\.\d+)?",
            availability,
        )

        if numbers:

            try:

                if float(numbers[0]) > 0:
                    return True

            except Exception:
                pass


    # --------------------------------------------------------
    # DEFAULT
    # --------------------------------------------------------

    return True


# ============================================================
# GET ALL AVAILABLE SUPPLIER PRODUCTS
# ============================================================

def get_available_supplier_products():

    try:

        response = (
            supabase
            .table("products")
            .select(
                """
                id,
                product_name,
                category,
                product_type,
                seller_id,
                seller_type,
                brand,
                description,
                quantity,
                unit,
                price_per_unit,
                availability,
                rating,
                supplier_location,
                image_url,
                status,
                created_at
                """
            )
            .eq("product_type", "supply")
            .eq("seller_type", "supplier")
            .execute()
        )

        products = response.data or []

        available_products = []

        for product in products:

            if is_product_available(product):

                available_products.append(
                    product
                )

        return available_products

    except Exception as e:

        print(
            "Error loading supplier products:",
            str(e),
        )

        return []


# ============================================================
# BUILD SEARCHABLE PRODUCT TEXT
# ============================================================

def build_product_search_text(
    product: dict,
) -> str:

    fields = [

        product.get(
            "product_name",
            "",
        ),

        product.get(
            "category",
            "",
        ),

        product.get(
            "brand",
            "",
        ),

        product.get(
            "description",
            "",
        ),

    ]

    return normalize_text(
        " ".join(
            str(field or "")
            for field in fields
        )
    )


# ============================================================
# SCORE PRODUCT RELEVANCE
# ============================================================

def score_product(
    product: dict,
    keywords: set,
    treatment: str,
    causes: str,
    prevention: str,
):

    product_name = normalize_text(
        product.get(
            "product_name",
            "",
        )
    )

    category = normalize_text(
        product.get(
            "category",
            "",
        )
    )

    brand = normalize_text(
        product.get(
            "brand",
            "",
        )
    )

    description = normalize_text(
        product.get(
            "description",
            "",
        )
    )

    product_text = build_product_search_text(
        product
    )


    treatment_text = normalize_text(
        treatment
    )

    causes_text = normalize_text(
        causes
    )

    prevention_text = normalize_text(
        prevention
    )


    score = 0

    matched_keywords = set()


    for keyword in keywords:

        keyword = normalize_text(
            keyword
        )

        if not keyword:
            continue


        # ----------------------------------------------------
        # PRODUCT NAME
        # Strongest match.
        # ----------------------------------------------------

        if keyword in product_name:

            score += 6

            matched_keywords.add(
                keyword
            )


        # ----------------------------------------------------
        # CATEGORY
        # ----------------------------------------------------

        if keyword in category:

            score += 5

            matched_keywords.add(
                keyword
            )


        # ----------------------------------------------------
        # BRAND
        # ----------------------------------------------------

        if keyword in brand:

            score += 3

            matched_keywords.add(
                keyword
            )


        # ----------------------------------------------------
        # DESCRIPTION
        # ----------------------------------------------------

        if keyword in description:

            score += 4

            matched_keywords.add(
                keyword
            )


    # ========================================================
    # CATEGORY / KEYWORD INTELLIGENCE
    # ========================================================

    normalized_category = normalize_category(
        product.get(
            "category",
            "",
        )
    )


    # --------------------------------------------------------
    # FUNGICIDE MATCH
    # --------------------------------------------------------

    fungal_terms = KEYWORD_GROUPS[
        "fungicide"
    ]

    fungal_diagnosis = any(
        normalize_text(term)
        in normalize_text(
            " ".join([
                treatment_text,
                causes_text,
            ])
        )
        for term in fungal_terms
    )

    if fungal_diagnosis:

        if (
            normalized_category == "fungicides"
            or "fungicide" in product_text
            or "fungal" in product_text
            or "copper" in product_text
        ):

            score += 15

            matched_keywords.add(
                "fungicide"
            )


    # --------------------------------------------------------
    # SPRAYER MATCH
    # --------------------------------------------------------

    sprayer_terms = KEYWORD_GROUPS[
        "sprayer"
    ]

    sprayer_diagnosis = any(
        normalize_text(term)
        in treatment_text
        for term in sprayer_terms
    )

    if sprayer_diagnosis:

        if (
            normalized_category == "sprayers"
            or "sprayer" in product_text
            or "knapsack" in product_text
        ):

            score += 10

            matched_keywords.add(
                "sprayer"
            )


    # --------------------------------------------------------
    # FERTILIZER MATCH
    # --------------------------------------------------------

    fertilizer_terms = KEYWORD_GROUPS[
        "fertilizer"
    ]

    fertilizer_diagnosis = any(
        normalize_text(term)
        in normalize_text(
            " ".join([
                treatment_text,
                prevention_text,
            ])
        )
        for term in fertilizer_terms
    )

    if fertilizer_diagnosis:

        if (
            normalized_category
            in {
                "soil products",
                "fertilizers",
            }
            or "fertilizer" in product_text
            or "npk" in product_text
        ):

            score += 10

            matched_keywords.add(
                "fertilizer"
            )


    return score, list(
        matched_keywords
    )


# ============================================================
# GET RULE-BASED RECOMMENDATIONS
# ============================================================

def get_disease_rules(
    crop_normalized: str,
    disease_normalized: str,
):

    try:

        response = (
            supabase
            .table(
                "disease_supply_recommendations"
            )
            .select(
                "crop,disease,category,reason,priority"
            )
            .eq(
                "crop",
                crop_normalized,
            )
            .eq(
                "disease",
                disease_normalized,
            )
            .execute()
        )

        return response.data or []

    except Exception as e:

        print(
            "Error loading disease rules:",
            str(e),
        )

        return []


# ============================================================
# PRIORITY FROM SCORE
# ============================================================

def priority_from_score(
    score: int,
) -> str:

    if score >= 15:
        return "high"

    if score >= 7:
        return "medium"

    return "low"


# ============================================================
# BUILD DEFAULT REASON
# ============================================================

def build_match_reason(
    category: str,
    matched_keywords: list,
):

    if matched_keywords:

        keywords_text = ", ".join(
            matched_keywords[:4]
        )

        return (
            f"Recommended based on diagnosis keywords: "
            f"{keywords_text}."
        )

    return (
        f"Products in the {category} category "
        f"may support the recommended treatment."
    )


# ============================================================
# GET DISEASE SUPPLY RECOMMENDATIONS
# ============================================================

@router.get("")
def get_supply_recommendations(

    crop: str = Query(...),

    disease: str = Query(...),

    severity: str = Query(
        "moderate"
    ),

    causes: str = Query(
        ""
    ),

    treatment: str = Query(
        ""
    ),

    prevention: str = Query(
        ""
    ),
):

    try:

        # ====================================================
        # NORMALIZE INPUT
        # ====================================================

        crop_normalized = normalize_text(
            crop
        )

        disease_normalized = normalize_text(
            disease
        )

        severity_normalized = normalize_text(
            severity
        )


        # ====================================================
        # EXTRACT DIAGNOSIS KEYWORDS
        # ====================================================

        keywords = extract_diagnosis_keywords(
            disease=disease,
            causes=causes,
            treatment=treatment,
            prevention=prevention,
        )


        print(
            "Recommendation keywords:",
            sorted(
                keywords
            ),
        )


        # ====================================================
        # LOAD ALL AVAILABLE SUPPLIER PRODUCTS
        # ====================================================

        products = (
            get_available_supplier_products()
        )


        # ====================================================
        # SCORE PRODUCTS
        # ====================================================

        matched_products = []

        for product in products:

            score, matched_keywords = (
                score_product(
                    product=product,
                    keywords=keywords,
                    treatment=treatment,
                    causes=causes,
                    prevention=prevention,
                )
            )

            # ------------------------------------------------
            # Only return genuinely relevant products.
            # ------------------------------------------------

            if score < 4:
                continue


            product_copy = dict(
                product
            )

            product_copy[
                "_match_score"
            ] = score

            product_copy[
                "_matched_keywords"
            ] = matched_keywords

            matched_products.append(
                product_copy
            )


        # ====================================================
        # SORT BEST MATCHES FIRST
        # ====================================================

        matched_products.sort(
            key=lambda item:
                item.get(
                    "_match_score",
                    0,
                ),
            reverse=True,
        )


        # ====================================================
        # GET DISEASE-SPECIFIC RULES
        # ====================================================

        disease_rules = get_disease_rules(
            crop_normalized,
            disease_normalized,
        )


        # ====================================================
        # GROUP PRODUCTS BY CATEGORY
        # ====================================================

        grouped_products = {}

        for product in matched_products:

            category = (
                product.get(
                    "category",
                    ""
                )
                or "Recommended Supplies"
            )

            if category not in grouped_products:

                grouped_products[
                    category
                ] = []

            grouped_products[
                category
            ].append(
                product
            )


        # ====================================================
        # BUILD RULE LOOKUP
        # ====================================================

        rules_by_category = {}

        for rule in disease_rules:

            category = rule.get(
                "category",
                ""
            )

            normalized = normalize_category(
                category
            )

            if normalized:

                rules_by_category[
                    normalized
                ] = rule


        # ====================================================
        # BUILD FINAL RECOMMENDATIONS
        # ====================================================

        final_recommendations = []

        seen_categories = set()


        # ----------------------------------------------------
        # FIRST:
        # Show categories containing matched products.
        # ----------------------------------------------------

        for category, category_products in (
            grouped_products.items()
        ):

            normalized_category = (
                normalize_category(
                    category
                )
            )

            if normalized_category in seen_categories:
                continue

            seen_categories.add(
                normalized_category
            )


            # Highest product score determines priority.
            highest_score = max(
                product.get(
                    "_match_score",
                    0,
                )
                for product
                in category_products
            )


            # Use disease rule if available.
            rule = rules_by_category.get(
                normalized_category
            )


            if rule:

                reason = rule.get(
                    "reason",
                    "",
                )

                priority = rule.get(
                    "priority",
                    "medium",
                )

            else:

                top_product = (
                    category_products[0]
                )

                reason = build_match_reason(
                    category,
                    top_product.get(
                        "_matched_keywords",
                        [],
                    ),
                )

                priority = priority_from_score(
                    highest_score
                )


            # Remove internal matching fields before
            # returning JSON to Flutter.
            clean_products = []

            for product in category_products:

                clean_product = dict(
                    product
                )

                clean_product.pop(
                    "_match_score",
                    None,
                )

                clean_product.pop(
                    "_matched_keywords",
                    None,
                )

                clean_products.append(
                    clean_product
                )


            final_recommendations.append(
                {
                    "category": category,
                    "reason": reason,
                    "priority": priority,
                    "products": clean_products,
                }
            )


        # ====================================================
        # OPTIONAL FALLBACK
        #
        # Keep disease rule categories even if no supplier
        # product currently matches.
        # ====================================================

        for rule in disease_rules:

            category = rule.get(
                "category",
                ""
            )

            normalized_category = (
                normalize_category(
                    category
                )
            )

            if normalized_category in seen_categories:
                continue

            seen_categories.add(
                normalized_category
            )

            final_recommendations.append(
                {
                    "category": category,
                    "reason": rule.get(
                        "reason",
                        "",
                    ),
                    "priority": rule.get(
                        "priority",
                        "medium",
                    ),
                    "products": [],
                }
            )


        # ====================================================
        # SORT RECOMMENDATIONS
        # ====================================================

        priority_order = {
            "high": 1,
            "medium": 2,
            "low": 3,
        }

        final_recommendations.sort(
            key=lambda item:
                priority_order.get(
                    str(
                        item.get(
                            "priority",
                            "medium",
                        )
                    ).lower(),
                    4,
                )
        )


        # ====================================================
        # RETURN RESPONSE
        # ====================================================

        return {
            "crop": crop_normalized,
            "disease": disease_normalized,
            "severity": severity_normalized,
            "recommendations":
                final_recommendations,
        }


    except Exception as e:

        print(
            "Supply recommendation error:",
            str(e),
        )

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
