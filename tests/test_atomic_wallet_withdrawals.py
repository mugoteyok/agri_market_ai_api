"""Offline tests for atomic wallet withdrawal routing and MTN reference safety."""
import asyncio
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import requests
from fastapi import HTTPException

from routers import wallet as wallet_router
from schemas.wallet import WithdrawalCreate
from services import mtn_service


SELLER_ID = "11111111-1111-4111-8111-111111111111"
TRANSACTION_ID = "22222222-2222-4222-8222-222222222222"
MTN_REFERENCE = "33333333-3333-4333-8333-333333333333"


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeWithdrawalQuery:
    def __init__(self, row):
        self.row = row

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        return FakeResult([self.row] if self.row else [])


class FakeAdmin:
    def __init__(self, reserve_result=None, rpc_results=None, withdrawal=None):
        self.reserve_result = reserve_result
        self.rpc_results = rpc_results or {}
        self.withdrawal = withdrawal
        self.rpc_calls = []

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        if name == "reserve_wallet_withdrawal":
            value = self.reserve_result
            if callable(value):
                value = value(params)
        else:
            value = self.rpc_results.get(name, {"result": "unexpected"})
        return FakeResult(value)

    def table(self, name):
        if name != "withdrawals":
            raise AssertionError(f"Unexpected table access: {name}")
        return FakeWithdrawalQuery(self.withdrawal)


def reserved_result(params):
    return {
        "result": "reserved",
        "withdrawal": {
            "transaction_id": params["p_transaction_id"],
            "mtn_reference_id": params["p_mtn_reference_id"],
            "status": "processing",
            "amount": params["p_amount"],
        },
    }


class AtomicWithdrawalRouteTests(TestCase):
    def setUp(self):
        self.profile = {
            "id": SELLER_ID,
            "role": "farmer",
            "mobile_money_number": "0771234567",
        }
        self.wallet = {
            "id": "44444444-4444-4444-8444-444444444444",
            "seller_id": SELLER_ID,
            "seller_type": "farmer",
            "balance": 9000,
        }
        self.user = SimpleNamespace(id=SELLER_ID)

    def test_withdrawal_reserves_before_mtn_and_reuses_saved_reference(self):
        admin = FakeAdmin(reserve_result=reserved_result)
        events = []

        def transfer(**kwargs):
            events.append(("mtn", kwargs))
            return {"accepted": True, "status_code": 202}

        with (
            patch.object(wallet_router, "get_profile", return_value=self.profile),
            patch.object(wallet_router, "get_wallet_record", return_value=self.wallet),
            patch.object(wallet_router, "validate_disbursement_config"),
            patch.object(wallet_router, "get_admin_supabase", return_value=admin),
            patch.object(wallet_router, "transfer_money", side_effect=transfer),
        ):
            result = asyncio.run(
                wallet_router.withdraw(
                    WithdrawalCreate(amount=1000),
                    self.user,
                )
            )

        self.assertEqual(result["status"], "processing")
        self.assertEqual(admin.rpc_calls[0][0], "reserve_wallet_withdrawal")
        reserve_args = admin.rpc_calls[0][1]
        self.assertEqual(events[0][0], "mtn")
        self.assertEqual(events[0][1]["external_id"], reserve_args["p_transaction_id"])
        self.assertEqual(events[0][1]["reference_id"], reserve_args["p_mtn_reference_id"])
        self.assertEqual(result["transaction_id"], reserve_args["p_transaction_id"])
        self.assertEqual(result["mtn_reference_id"], reserve_args["p_mtn_reference_id"])

    def test_mtn_http_409_keeps_funds_reserved(self):
        admin = FakeAdmin(reserve_result=reserved_result)

        with (
            patch.object(wallet_router, "get_profile", return_value=self.profile),
            patch.object(wallet_router, "get_wallet_record", return_value=self.wallet),
            patch.object(wallet_router, "validate_disbursement_config"),
            patch.object(wallet_router, "get_admin_supabase", return_value=admin),
            patch.object(
                wallet_router,
                "transfer_money",
                return_value={"accepted": False, "status_code": 409},
            ),
        ):
            result = asyncio.run(
                wallet_router.withdraw(WithdrawalCreate(amount=1000), self.user)
            )

        self.assertEqual(result["status"], "processing")
        self.assertTrue(result["reconciliation_required"])
        self.assertEqual(
            [name for name, _ in admin.rpc_calls],
            ["reserve_wallet_withdrawal"],
        )

    def test_ambiguous_mtn_http_responses_keep_funds_reserved(self):
        for status_code in (None, 100, 200, 201, 204, 302, 307, 425, 500, 503):
            with self.subTest(status_code=status_code):
                admin = FakeAdmin(reserve_result=reserved_result)

                with (
                    patch.object(wallet_router, "get_profile", return_value=self.profile),
                    patch.object(wallet_router, "get_wallet_record", return_value=self.wallet),
                    patch.object(wallet_router, "validate_disbursement_config"),
                    patch.object(wallet_router, "get_admin_supabase", return_value=admin),
                    patch.object(
                        wallet_router,
                        "transfer_money",
                        return_value={"accepted": False, "status_code": status_code},
                    ),
                ):
                    result = asyncio.run(
                        wallet_router.withdraw(WithdrawalCreate(amount=1000), self.user)
                    )

                self.assertEqual(result["status"], "processing")
                self.assertTrue(result["reconciliation_required"])
                self.assertEqual(
                    [name for name, _ in admin.rpc_calls],
                    ["reserve_wallet_withdrawal"],
                )

    def test_network_outcome_unknown_keeps_funds_reserved(self):
        admin = FakeAdmin(reserve_result=reserved_result)

        with (
            patch.object(wallet_router, "get_profile", return_value=self.profile),
            patch.object(wallet_router, "get_wallet_record", return_value=self.wallet),
            patch.object(wallet_router, "validate_disbursement_config"),
            patch.object(wallet_router, "get_admin_supabase", return_value=admin),
            patch.object(
                wallet_router,
                "transfer_money",
                side_effect=mtn_service.MTNTransferOutcomeUnknown("timeout"),
            ),
        ):
            result = asyncio.run(
                wallet_router.withdraw(WithdrawalCreate(amount=1000), self.user)
            )

        self.assertEqual(result["status"], "processing")
        self.assertTrue(result["reconciliation_required"])
        self.assertEqual(
            [name for name, _ in admin.rpc_calls],
            ["reserve_wallet_withdrawal"],
        )

    def _withdrawal_row(self, reserved=True):
        return {
            "id": "55555555-5555-4555-8555-555555555555",
            "transaction_id": TRANSACTION_ID,
            "mtn_reference_id": MTN_REFERENCE,
            "seller_id": SELLER_ID,
            "seller_type": "farmer",
            "farmer_id": SELLER_ID,
            "amount": 1000,
            "status": "processing",
            "funds_reserved": reserved,
        }

    def test_confirmed_success_calls_completion_rpc_only(self):
        admin = FakeAdmin(
            withdrawal=self._withdrawal_row(),
            rpc_results={
                "complete_wallet_withdrawal": {
                    "result": "completed",
                    "withdrawal": {"status": "completed"},
                }
            },
        )

        with (
            patch.object(wallet_router, "get_admin_supabase", return_value=admin),
            patch.object(wallet_router, "get_wallet_record", return_value=self.wallet),
            patch.object(
                wallet_router,
                "get_transfer_status",
                return_value={
                    "status": "SUCCESSFUL",
                    "financialTransactionId": "mtn-financial-id",
                },
        ),
        ):
            result = asyncio.run(
                wallet_router.confirm_withdrawal(TRANSACTION_ID, self.user)
            )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(
            [name for name, _ in admin.rpc_calls],
            ["complete_wallet_withdrawal"],
        )

    def test_confirmed_failure_calls_release_rpc_only(self):
        admin = FakeAdmin(
            withdrawal=self._withdrawal_row(),
            rpc_results={
                "release_wallet_withdrawal": {
                    "result": "released",
                    "withdrawal": {"status": "failed"},
                }
            },
        )

        with (
            patch.object(wallet_router, "get_admin_supabase", return_value=admin),
            patch.object(wallet_router, "get_wallet_record", return_value=self.wallet),
            patch.object(
                wallet_router,
                "get_transfer_status",
                return_value={"status": "FAILED", "reason": "Provider rejected payout"},
            ),
        ):
            result = asyncio.run(
                wallet_router.confirm_withdrawal(TRANSACTION_ID, self.user)
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(
            [name for name, _ in admin.rpc_calls],
            ["release_wallet_withdrawal"],
        )

    def test_legacy_unreserved_withdrawal_is_not_sent_to_mtn(self):
        admin = FakeAdmin(withdrawal=self._withdrawal_row(reserved=False))

        with (
            patch.object(wallet_router, "get_admin_supabase", return_value=admin),
            patch.object(wallet_router, "get_transfer_status") as status_mock,
        ):
            with self.assertRaises(HTTPException) as context:
                asyncio.run(
                    wallet_router.confirm_withdrawal(TRANSACTION_ID, self.user)
                )

        self.assertEqual(context.exception.status_code, 409)
        status_mock.assert_not_called()
        self.assertEqual(admin.rpc_calls, [])


class MTNTransferReferenceTests(TestCase):
    def test_transfer_uses_preallocated_reference_id(self):
        fake_response = SimpleNamespace(status_code=202, text="accepted")

        with (
            patch.object(mtn_service, "validate_disbursement_config"),
            patch.object(mtn_service, "get_disbursement_access_token", return_value="test-token"),
            patch.object(mtn_service.requests, "post", return_value=fake_response) as post,
        ):
            result = mtn_service.transfer_money(
                amount=1000,
                phone_number="256771234567",
                external_id=TRANSACTION_ID,
                reference_id=MTN_REFERENCE,
            )

        self.assertTrue(result["accepted"])
        self.assertEqual(result["reference_id"], MTN_REFERENCE)
        self.assertEqual(post.call_args.kwargs["headers"]["X-Reference-Id"], MTN_REFERENCE)

    def test_transfer_timeout_is_marked_outcome_unknown(self):
        with (
            patch.object(mtn_service, "validate_disbursement_config"),
            patch.object(mtn_service, "get_disbursement_access_token", return_value="test-token"),
            patch.object(
                mtn_service.requests,
                "post",
                side_effect=requests.Timeout("simulated timeout"),
            ),
        ):
            with self.assertRaises(mtn_service.MTNTransferOutcomeUnknown):
                mtn_service.transfer_money(
                    amount=1000,
                    phone_number="256771234567",
                    external_id=TRANSACTION_ID,
                    reference_id=MTN_REFERENCE,
                )


if __name__ == "__main__":
    import unittest
    unittest.main()

# Supabase RPC mock: mirror the real query builder's execute() method.
FakeResult.execute = lambda self: self
