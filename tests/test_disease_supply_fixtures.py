"""Offline integration tests for disease/pest-to-supplier matching.

All products below are synthetic test fixtures based on product descriptions
published by Growmate Uganda. They are not real inventory and are never written
or uploaded to Supabase. Recheck current Uganda registration/labels separately
before using any catalogue data for farmer-facing advice.

Source references used to construct the test examples:
- https://growmate.co.ug/product/absolute-star-400-sc/
- https://growmate.co.ug/product/biosquare-32-wp/
- https://growmate.co.ug/product/kingdom-780-wg/
- https://growmate.co.ug/product/pyrazole-500-ec/
"""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from routers import disease_supply_matches as matcher


TEST_RULES = [
    {"crop": "coffee", "disease": "coffee leaf rust", "category": "Fungicides", "reason": "Fixture rule", "priority": "high"},
    {"crop": "maize", "disease": "fall armyworm", "category": "Pest Control", "reason": "Fixture rule", "priority": "high"},
    {"crop": "tomato", "disease": "late blight", "category": "Fungicides", "reason": "Fixture rule", "priority": "high"},
    {"crop": "beans", "disease": "rust", "category": "Fungicides", "reason": "Fixture rule", "priority": "high"},
]


def make_product(product_id, name, crop, category, active_ingredient, pathogens, target_field, target, description):
    tags = {
        "category": "treatment",
        "pathogens": [pathogens],
        "crop_types": [crop],
        "spray_based": True,
        "active_ingredient": active_ingredient,
        target_field: [target],
    }
    return {
        "id": product_id,
        "product_name": name,
        "description": description,
        "crop": crop,
        "category": category,
        "brand": name.split()[0],
        "quantity": 10,
        "unit": "pack",
        "price_per_unit": 1000,
        "region": "Kampala",
        "image_url": None,
        "image_urls": [],
        "status": "available",
        "created_at": "2026-01-01T00:00:00Z",
        "seller_id": "fixture-supplier",
        "seller_type": "supplier",
        "product_type": "supply",
        "availability": "in_stock",
        "rating": 0,
        "supplier_location": "Kampala",
        "recommendation_tags": tags,
    }


TEST_PRODUCTS = [
    make_product(
        "fixture-coffee-rust", "Absolute Star 400 SC", "coffee", "Pesticides",
        "Azoxystrobin 250 g/L + Difenoconazole 150 g/L", "fungal",
        "treats_diseases", "coffee leaf rust", "Published source lists coffee leaf rust and coffee.",
    ),
    make_product(
        "fixture-fall-armyworm", "Biosquare 32 WP", "maize", "Pesticides",
        "Bacillus thuringiensis aizawai KN-11 32000 IU/mg", "insect",
        "treats_pests", "fall armyworm", "Published source lists maize and fall armyworm.",
    ),
    make_product(
        "fixture-tomato-blight", "Kingdom 780 WG", "tomato", "Pesticides",
        "Mancozeb 600 g/kg + Dimethomorph 100 g/kg + Cymoxanil 80 g/kg", "oomycete",
        "treats_diseases", "late blight", "Published source lists tomato and late blight.",
    ),
    make_product(
        "fixture-beans-rust", "Pyrazole 500 EC", "beans", "Pesticides",
        "Difenoconazole 300 g/L + Pyraclostrobin 200 g/L", "fungal",
        "treats_diseases", "rust", "Published source lists beans and rust.",
    ),
]


class FakeQuery:
    def __init__(self, rows):
        self.rows = list(rows)
        self.filters = []
        self.maximum = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, field, value):
        self.filters.append(("eq", field, value))
        return self

    def in_(self, field, values):
        self.filters.append(("in", field, set(values)))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, count):
        self.maximum = count
        return self

    def execute(self):
        rows = self.rows
        for kind, field, value in self.filters:
            if kind == "eq":
                rows = [row for row in rows if row.get(field) == value]
            else:
                rows = [row for row in rows if row.get(field) in value]
        if self.maximum is not None:
            rows = rows[: self.maximum]
        return SimpleNamespace(data=deepcopy(rows))


class FakeClient:
    def __init__(self, rules=None, products=None):
        self.tables = {
            "disease_supply_recommendations": rules or [],
            "products": products or [],
            "business_profiles": [],
        }

    def table(self, name):
        return FakeQuery(self.tables.get(name, []))


class DiseaseSupplyFixtureTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient(TEST_RULES, TEST_PRODUCTS)

    def recommend(self, crop, diagnosis):
        with patch.object(matcher, "_get_service_client", return_value=self.client):
            return matcher.get_disease_supply_matches(
                crop=crop,
                disease=diagnosis,
                diagnosis_status="disease",
                _user={"id": "offline-test-user"},
            )

    def treatment_names(self, result):
        return [
            product["product_name"]
            for group in result["recommendations"]
            if group["section"] == "treatment"
            for product in group["products"]
        ]

    def test_all_four_diagnoses_match_their_fixture_product(self):
        cases = [
            ("coffee", "coffee leaf rust", "Absolute Star 400 SC"),
            ("maize", "fall armyworm", "Biosquare 32 WP"),
            ("tomato", "late blight", "Kingdom 780 WG"),
            ("beans", "rust", "Pyrazole 500 EC"),
        ]
        for crop, diagnosis, expected in cases:
            with self.subTest(crop=crop, diagnosis=diagnosis):
                result = self.recommend(crop, diagnosis)
                self.assertIn(expected, self.treatment_names(result))

    def test_fall_armyworm_requires_explicit_treats_pests_tag(self):
        generic_insecticide = make_product(
            "fixture-generic-insecticide", "Generic insecticide", "maize", "Pesticides",
            "Unspecified active ingredient", "insect", "treats_diseases", "", "Decoy fixture.",
        )
        generic_insecticide["recommendation_tags"].pop("treats_diseases", None)
        self.client.tables["products"].append(generic_insecticide)
        result = self.recommend("maize", "fall armyworm")
        names = self.treatment_names(result)
        self.assertIn("Biosquare 32 WP", names)
        self.assertNotIn("Generic insecticide", names)

    def test_product_for_another_crop_is_not_recommended(self):
        self.client.tables["disease_supply_recommendations"].append(
            {"crop": "maize", "disease": "coffee leaf rust", "category": "Fungicides", "reason": "Negative fixture", "priority": "high"}
        )
        result = self.recommend("maize", "coffee leaf rust")
        self.assertEqual([], self.treatment_names(result))

    def test_tools_are_not_returned_without_a_matching_treatment(self):
        self.client.tables["disease_supply_recommendations"] = [
            {"crop": "beans", "disease": "unlisted condition", "category": "Sprayers", "reason": "Fixture", "priority": "medium"},
            {"crop": "beans", "disease": "unlisted condition", "category": "Protective Equipment", "reason": "Fixture", "priority": "medium"},
        ]
        self.client.tables["products"] = [
            {
                "id": "fixture-sprayer", "product_name": "Knapsack sprayer", "quantity": 5,
                "status": "available", "availability": "in_stock", "seller_type": "supplier",
                "product_type": "supply", "seller_id": "fixture-supplier",
                "recommendation_tags": {"category": "tool", "tool_type": "sprayer", "crop_types": []},
            },
            {
                "id": "fixture-ppe", "product_name": "Protective equipment", "quantity": 5,
                "status": "available", "availability": "in_stock", "seller_type": "supplier",
                "product_type": "supply", "seller_id": "fixture-supplier",
                "recommendation_tags": {"category": "tool", "tool_type": "ppe", "crop_types": []},
            },
        ]
        result = self.recommend("beans", "unlisted condition")
        self.assertEqual([], result["recommendations"])


    def test_broad_pesticide_rule_does_not_infer_insect_target(self):
        self.client.tables['disease_supply_recommendations'] = [
            {'crop': 'maize', 'disease': 'aphid infestation', 'category': 'Pesticides', 'reason': 'Fixture', 'priority': 'high'}
        ]
        generic = make_product(
            'fixture-generic-pesticide', 'Generic insecticide', 'maize', 'Pesticides',
            'Unspecified ingredient', 'insect', 'treats_diseases', '', 'Generic decoy.'
        )
        generic['recommendation_tags'].pop('treats_diseases', None)
        self.client.tables['products'] = [generic]
        result = self.recommend('maize', 'aphid infestation')
        self.assertEqual([], self.treatment_names(result))

if __name__ == "__main__":
    unittest.main(verbosity=2)
