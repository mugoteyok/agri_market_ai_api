from unittest import TestCase
from unittest.mock import patch

from services import mtn_service


class SandboxMsisdnTests(TestCase):
    TEST_NUMBERS = {
        "46733123450",
        "46733123451",
        "46733123452",
        "46733123453",
        "46733123454",
        "56733123453",
    }

    def test_all_documented_sandbox_numbers_are_allowed_when_enabled(self):
        with (
            patch.object(mtn_service, "MTN_ENVIRONMENT", "sandbox"),
            patch.object(mtn_service, "MTN_ALLOW_SANDBOX_TEST_MSISDNS", True),
        ):
            for number in self.TEST_NUMBERS:
                with self.subTest(number=number):
                    self.assertEqual(mtn_service.normalize_collection_msisdn(number), number)

    def test_sandbox_numbers_are_rejected_when_opt_in_is_disabled(self):
        with (
            patch.object(mtn_service, "MTN_ENVIRONMENT", "sandbox"),
            patch.object(mtn_service, "MTN_ALLOW_SANDBOX_TEST_MSISDNS", False),
        ):
            for number in self.TEST_NUMBERS:
                with self.subTest(number=number):
                    with self.assertRaises(ValueError):
                        mtn_service.normalize_collection_msisdn(number)

    def test_sandbox_numbers_are_rejected_outside_sandbox(self):
        with (
            patch.object(mtn_service, "MTN_ENVIRONMENT", "mtnuganda"),
            patch.object(mtn_service, "MTN_ALLOW_SANDBOX_TEST_MSISDNS", True),
        ):
            for number in self.TEST_NUMBERS:
                with self.subTest(number=number):
                    with self.assertRaises(ValueError):
                        mtn_service.normalize_collection_msisdn(number)

    def test_local_uganda_number_keeps_existing_normalization(self):
        with patch.object(mtn_service, "MTN_ALLOW_SANDBOX_TEST_MSISDNS", False):
            self.assertEqual(mtn_service.normalize_collection_msisdn("0772123456"), "256772123456")

    def test_international_uganda_number_is_preserved(self):
        with patch.object(mtn_service, "MTN_ALLOW_SANDBOX_TEST_MSISDNS", False):
            self.assertEqual(mtn_service.normalize_collection_msisdn("+256772123456"), "256772123456")

    def test_invalid_number_is_rejected(self):
        with patch.object(mtn_service, "MTN_ALLOW_SANDBOX_TEST_MSISDNS", False):
            with self.assertRaises(ValueError):
                mtn_service.normalize_collection_msisdn("not-a-number")

    def test_unknown_non_uganda_number_is_not_accepted_by_allowlist(self):
        with (
            patch.object(mtn_service, "MTN_ENVIRONMENT", "sandbox"),
            patch.object(mtn_service, "MTN_ALLOW_SANDBOX_TEST_MSISDNS", True),
        ):
            with self.assertRaises(ValueError):
                mtn_service.normalize_collection_msisdn("46733123499")
