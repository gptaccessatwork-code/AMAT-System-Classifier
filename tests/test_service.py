import unittest
from unittest.mock import patch

from system_type_identifier.config import AppSettings
from system_type_identifier.models import DecisionStatus
from system_type_identifier.service import SystemMatcherService, display_result


class SystemMatcherServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = SystemMatcherService(AppSettings())

    def test_direct_lookup_returns_system_type_and_template_without_agile(self):
        classification = self.service.classify_one("707844-XA3-GPA")

        self.assertEqual(classification.decision.status, DecisionStatus.CLASSIFIED)
        result = display_result(classification)
        self.assertEqual(result.system_type, "ETCH SYM3 AP (XA)")
        self.assertEqual(result.wd_template, "SGP_TEMPLATE_AMAT_SYM3")

    def test_invalid_lookup_is_rejected_without_agile(self):
        classification = self.service.classify_one("500678N123-DX-GPB")

        self.assertEqual(
            classification.decision.status,
            DecisionStatus.EXCLUDED_INVALID_FORMAT,
        )
        result = display_result(classification)
        self.assertEqual(result.system_type, "")
        self.assertEqual(result.wd_template, "")

    def test_bom_lookup_requires_user_sign_in(self):
        with self.assertRaisesRegex(RuntimeError, "Sign in to Agile"):
            self.service.classify_one("510284-DX-GPB")

    @patch("system_type_identifier.service.AgileBomClient")
    def test_sign_in_session_is_closed_on_sign_out(self, client_type):
        client = client_type.return_value

        self.service.sign_in("engineer", "secret")
        self.assertTrue(self.service.signed_in)
        client_type.assert_called_once_with(
            "engineer",
            "secret",
            wsdl_url=self.service.settings.wsdl_url,
        )

        self.service.sign_out()
        self.assertFalse(self.service.signed_in)
        client.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
