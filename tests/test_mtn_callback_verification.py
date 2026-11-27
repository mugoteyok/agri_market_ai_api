# Callback regression tests: callback body is never payment authority.
import asyncio
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.routing import APIRoute

from routers import mtn_callback


ORDER = {
    "id": "11111111-1111-4111-8111-111111111111",
    "buyer_id": "22222222-2222-4222-8222-222222222222",
    "seller_id": "33333333-3333-4333-8333-333333333333",
    "crop": "Maize",
    "quantity": 2,
    "total_amount": "3000.00",
    "payment_status": "pending",
    "payment_method": "Mobile Money",
    "payment_reference": "44444444-4444-4444-8444-444444444444",
    "payment_external_id": "payment-external-123",
    "order_status": "accepted",
    "stock_reserved": True,
    "stock_released": False,
}
PROVIDER_SUCCESS = {
    "status": "SUCCESSFUL",
    "externalId": "payment-external-123",
    "amount": "3000",
    "currency": "EUR",
    "financialTransactionId": "mtn-fin-123",
}
PROVIDER_FAILURE = {**PROVIDER_SUCCESS, "status": "FAILED"}


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, admin):
        self.admin = admin
        self.filters = []
        self.action = "select"
        self.update_data = None
        self.columns = "*"

    def select(self, columns):
        self.action = "select"
        self.columns = columns
        return self

    def update(self, values):
        self.action = "update"
        self.update_data = values
        return self

    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self

    def neq(self, column, value):
        self.filters.append(("neq", column, value))
        return self

    def limit(self, _limit):
        return self

    def _matches(self):
        for operator, column, value in self.filters:
            actual = self.admin.order.get(column)
            if operator == "eq" and actual != value:
                return False
            if operator == "neq" and actual == value:
                return False
        return True

    def execute(self):
        if not self._matches() or not self.admin.order:
            return FakeResult([])

        if self.action == "update":
            self.admin.order.update(self.update_data)
            self.admin.updates.append(deepcopy(self.update_data))
            return FakeResult([deepcopy(self.admin.order)])

        if self.columns == "payment_status":
            return FakeResult([{
                "payment_status": self.admin.order.get("payment_status")
            }])

        return FakeResult([deepcopy(self.admin.order)])


class FakeRpc:
    def __init__(self, admin, name, params):
        self.admin = admin
        self.name = name
        self.params = params

    def execute(self):
        self.admin.rpc_calls.append((self.name, self.params))
        if self.name != "apply_mtn_collection_result":
            raise AssertionError(f"Unexpected RPC: {self.name}")

        status = self.params["p_provider_status"]
        current = str(self.admin.order.get("payment_status") or "pending").lower()

        if status == "SUCCESSFUL":
            if current == "paid":
                return FakeResult({
                    "processed": True,
                    "newly_paid": False,
                    "payment_status": "paid",
                    "reconciliation_required": bool(
                        self.admin.order.get("payment_reconciliation_required")
                    ),
                })

            reason = None
            if current == "failed":
                reason = "MTN confirmed payment success after the order was marked failed."
            elif str(self.admin.order.get("order_status") or "").lower() == "cancelled":
                reason = "MTN confirmed payment success after the order was cancelled."
            elif self.admin.order.get("stock_released") is True:
                reason = "MTN confirmed payment success after reserved stock was released."

            required = bool(
                self.admin.order.get("payment_reconciliation_required")
            ) or reason is not None
            self.admin.order.update({
                "payment_status": "paid",
                "payment_reconciliation_required": required,
                "payment_reconciliation_reason": (
                    self.admin.order.get("payment_reconciliation_reason") or reason
                ),
            })
            return FakeResult({
                "processed": True,
                "newly_paid": True,
                "payment_status": "paid",
                "reconciliation_required": required,
                "reconciliation_reason": reason,
            })

        if current == "paid":
            return FakeResult({
                "processed": True,
                "newly_failed": False,
                "payment_status": "paid",
                "stock_released": False,
                "reconciliation_required": bool(
                    self.admin.order.get("payment_reconciliation_required")
                ),
            })

        newly_failed = current != "failed"
        release = (
            self.admin.order.get("stock_reserved") is True
            and self.admin.order.get("stock_released") is not True
        )
        self.admin.order.update({
            "payment_status": "failed",
            "order_status": "cancelled",
            "status": "cancelled",
        })
        if release:
            self.admin.order.update({
                "stock_reserved": False,
                "stock_released": True,
            })
        return FakeResult({
            "processed": True,
            "newly_failed": newly_failed,
            "payment_status": "failed",
            "stock_released": release,
            "already_released": (
                self.admin.order.get("stock_released") is True and not release
            ),
        })


class FakeAdmin:
    def __init__(self, order=None):
        self.order = deepcopy(order or ORDER)
        self.updates = []
        self.rpc_calls = []
        self.table_calls = []

    def table(self, name):
        self.table_calls.append(name)
        if name != "orders":
            raise AssertionError(f"Unexpected table: {name}")
        return FakeQuery(self)

    def rpc(self, name, params):
        return FakeRpc(self, name, params)


class FakeRequest:
    def __init__(self, payload):
        self.payload = payload

    async def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class MTNCallbackVerificationTests(TestCase):
    def setUp(self):
        self.admin = FakeAdmin()
        self.payload = {
            "externalId": "payment-external-123",
            "status": "SUCCESSFUL",
            "amount": "3000",
            "currency": "EUR",
        }

    def call_callback(self, payload=None):
        return asyncio.run(
            mtn_callback.mtn_callback(
                FakeRequest(self.payload if payload is None else payload)
            )
        )

    def test_forged_success_callback_does_not_mark_pending_payment_paid(self):
        with (
            patch.object(mtn_callback, "get_admin_supabase", return_value=self.admin),
            patch.object(
                mtn_callback,
                "get_payment_status",
                return_value={**PROVIDER_SUCCESS, "status": "PENDING"},
            ) as status_mock,
            patch.object(mtn_callback, "notify_buyer"),
            patch.object(mtn_callback, "notify_seller"),
        ):
            result = self.call_callback()

        self.assertFalse(result["processed"])
        self.assertEqual(self.admin.order["payment_status"], "pending")
        self.assertEqual(self.admin.updates, [])
        status_mock.assert_called_once_with(ORDER["payment_reference"])

    def test_verified_mtn_success_marks_order_paid_even_if_callback_claims_failure(self):
        with (
            patch.object(mtn_callback, "get_admin_supabase", return_value=self.admin),
            patch.object(mtn_callback, "get_payment_status", return_value=PROVIDER_SUCCESS),
            patch.object(mtn_callback, "notify_buyer") as buyer,
            patch.object(mtn_callback, "notify_seller") as seller,
        ):
            result = self.call_callback({
                "externalId": "payment-external-123",
                "status": "FAILED",
            })

        self.assertTrue(result["processed"])
        self.assertEqual(self.admin.order["payment_status"], "paid")
        self.assertEqual(
            self.admin.rpc_calls,
            [("apply_mtn_collection_result", {
                "p_order_id": ORDER["id"],
                "p_external_id": ORDER["payment_external_id"],
                "p_provider_status": "SUCCESSFUL",
            })],
        )
        self.assertEqual(self.admin.updates, [])
        buyer.assert_called_once()
        seller.assert_called_once()

    def test_mismatched_provider_amount_does_not_mark_order_paid(self):
        bad = {**PROVIDER_SUCCESS, "amount": "3001"}
        with (
            patch.object(mtn_callback, "get_admin_supabase", return_value=self.admin),
            patch.object(mtn_callback, "get_payment_status", return_value=bad),
        ):
            result = self.call_callback()

        self.assertFalse(result["processed"])
        self.assertTrue(result["reconciliation_required"])
        self.assertEqual(self.admin.order["payment_status"], "pending")
        self.assertEqual(self.admin.updates, [])

    def test_mismatched_provider_external_id_does_not_mark_order_paid(self):
        bad = {**PROVIDER_SUCCESS, "externalId": "another-payment"}
        with (
            patch.object(mtn_callback, "get_admin_supabase", return_value=self.admin),
            patch.object(mtn_callback, "get_payment_status", return_value=bad),
        ):
            result = self.call_callback()

        self.assertFalse(result["processed"])
        self.assertEqual(self.admin.order["payment_status"], "pending")
        self.assertEqual(self.admin.updates, [])

    def test_verified_mtn_failure_releases_reserved_stock(self):
        with (
            patch.object(mtn_callback, "get_admin_supabase", return_value=self.admin),
            patch.object(mtn_callback, "get_payment_status", return_value=PROVIDER_FAILURE),
            patch.object(mtn_callback, "notify_buyer"),
            patch.object(mtn_callback, "notify_seller"),
        ):
            result = self.call_callback()

        self.assertTrue(result["processed"])
        self.assertEqual(self.admin.order["payment_status"], "failed")
        self.assertEqual(
            self.admin.rpc_calls,
            [("apply_mtn_collection_result", {
                "p_order_id": ORDER["id"],
                "p_external_id": ORDER["payment_external_id"],
                "p_provider_status": "FAILED",
            })],
        )

    def test_late_verified_success_after_failure_is_flagged_for_reconciliation(self):
        late_order = {
            **ORDER,
            "payment_status": "failed",
            "order_status": "cancelled",
            "stock_reserved": False,
            "stock_released": True,
        }
        admin = FakeAdmin(late_order)
        with (
            patch.object(mtn_callback, "get_admin_supabase", return_value=admin),
            patch.object(mtn_callback, "get_payment_status", return_value=PROVIDER_SUCCESS),
            patch.object(mtn_callback, "notify_buyer"),
            patch.object(mtn_callback, "notify_seller"),
        ):
            result = asyncio.run(
                mtn_callback.mtn_callback(FakeRequest(self.payload))
            )

        self.assertTrue(result["processed"])
        self.assertEqual(admin.order["payment_status"], "paid")
        self.assertTrue(admin.order["payment_reconciliation_required"])
        self.assertTrue(result["reconciliation_required"])
        self.assertTrue(admin.order["stock_released"])

    def test_verified_failure_after_stock_already_released_does_not_release_again(self):
        cancelled_order = {
            **ORDER,
            "order_status": "cancelled",
            "stock_reserved": False,
            "stock_released": True,
        }
        admin = FakeAdmin(cancelled_order)
        with (
            patch.object(mtn_callback, "get_admin_supabase", return_value=admin),
            patch.object(mtn_callback, "get_payment_status", return_value=PROVIDER_FAILURE),
            patch.object(mtn_callback, "notify_buyer"),
            patch.object(mtn_callback, "notify_seller"),
        ):
            result = asyncio.run(
                mtn_callback.mtn_callback(FakeRequest(self.payload))
            )

        self.assertTrue(result["processed"])
        self.assertEqual(admin.order["payment_status"], "failed")
        self.assertFalse(result["stock_released"])
        self.assertTrue(result["already_released"])

    def test_duplicate_paid_callback_is_idempotent(self):
        admin = FakeAdmin({**ORDER, "payment_status": "paid"})
        with (
            patch.object(mtn_callback, "get_admin_supabase", return_value=admin),
            patch.object(mtn_callback, "get_payment_status") as status_mock,
        ):
            result = asyncio.run(
                mtn_callback.mtn_callback(FakeRequest(self.payload))
            )

        self.assertTrue(result["processed"])
        status_mock.assert_not_called()
        self.assertEqual(admin.updates, [])
        self.assertEqual(admin.rpc_calls, [])

    def test_callback_missing_external_id_does_not_query_database(self):
        with patch.object(mtn_callback, "get_admin_supabase", return_value=self.admin):
            result = self.call_callback({"status": "SUCCESSFUL"})

        self.assertFalse(result["processed"])
        self.assertEqual(self.admin.table_calls, [])

    def test_callback_supports_post_and_put(self):
        route = next(
            route for route in mtn_callback.router.routes
            if isinstance(route, APIRoute) and route.path == "/mtn/callback"
        )
        self.assertEqual(route.methods, {"POST", "PUT"})
