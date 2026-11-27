# Regression tests for matching MTN collection status to an order.
from unittest import TestCase
from unittest.mock import Mock, patch

from services import mtn_service


class CollectionPaymentVerificationTests(TestCase):
    def setUp(self):
        self.order = {
            "payment_external_id": "payment-ext-123",
            "total_amount": "3000.00",
        }
        self.provider_status = {
            "externalId": "payment-ext-123",
            "amount": "3000",
            "currency": "EUR",
            "status": "SUCCESSFUL",
            "financialTransactionId": "mtn-fin-123",
        }

    def test_matching_provider_response_is_accepted(self):
        with patch.object(mtn_service, "MTN_CURRENCY", "EUR"):
            self.assertIsNone(
                mtn_service.verify_collection_payment(
                    self.order, self.provider_status
                )
            )

    def test_mismatched_external_id_is_rejected(self):
        bad = {**self.provider_status, "externalId": "another-payment"}
        with patch.object(mtn_service, "MTN_CURRENCY", "EUR"):
            with self.assertRaisesRegex(ValueError, "externalId"):
                mtn_service.verify_collection_payment(self.order, bad)

    def test_mismatched_amount_is_rejected(self):
        bad = {**self.provider_status, "amount": "3001"}
        with patch.object(mtn_service, "MTN_CURRENCY", "EUR"):
            with self.assertRaisesRegex(ValueError, "amount"):
                mtn_service.verify_collection_payment(self.order, bad)

    def test_mismatched_currency_is_rejected(self):
        bad = {**self.provider_status, "currency": "UGX"}
        with patch.object(mtn_service, "MTN_CURRENCY", "EUR"):
            with self.assertRaisesRegex(ValueError, "currency"):
                mtn_service.verify_collection_payment(self.order, bad)

    def test_missing_external_id_is_rejected(self):
        bad_order = {**self.order, "payment_external_id": None}
        with patch.object(mtn_service, "MTN_CURRENCY", "EUR"):
            with self.assertRaisesRegex(ValueError, "externalId"):
                mtn_service.verify_collection_payment(bad_order, self.provider_status)

    def test_non_finite_amount_is_rejected(self):
        bad = {**self.provider_status, "amount": "NaN"}
        with patch.object(mtn_service, "MTN_CURRENCY", "EUR"):
            with self.assertRaisesRegex(ValueError, "amount"):
                mtn_service.verify_collection_payment(self.order, bad)

    def test_missing_currency_is_rejected(self):
        bad = {**self.provider_status, "currency": ""}
        with patch.object(mtn_service, "MTN_CURRENCY", "EUR"):
            with self.assertRaisesRegex(ValueError, "currency"):
                mtn_service.verify_collection_payment(self.order, bad)

    def test_transition_helper_rejects_mismatched_details_before_database_rpc(self):
        order = {**self.order, "id": "order-123"}
        bad = {**self.provider_status, "amount": "3001"}
        admin = Mock()
        with patch.object(mtn_service, "MTN_CURRENCY", "EUR"):
            with self.assertRaisesRegex(ValueError, "amount"):
                mtn_service.apply_collection_payment_result(order, bad, admin)
        admin.rpc.assert_not_called()

    def test_transition_helper_calls_rpc_only_after_verification(self):
        order = {**self.order, "id": "order-123"}
        admin = Mock()
        admin.rpc.return_value.execute.return_value.data = {
            "processed": True, "newly_paid": True
        }
        with patch.object(mtn_service, "MTN_CURRENCY", "EUR"):
            result = mtn_service.apply_collection_payment_result(
                order, self.provider_status, admin
            )
        self.assertTrue(result["processed"])
        admin.rpc.assert_called_once_with(
            "apply_mtn_collection_result",
            {
                "p_order_id": "order-123",
                "p_external_id": "payment-ext-123",
                "p_provider_status": "SUCCESSFUL",
            },
        )
