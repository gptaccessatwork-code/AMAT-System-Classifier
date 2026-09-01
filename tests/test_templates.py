import unittest

from system_type_identifier.models import ClassificationDecision, DecisionStatus
from system_type_identifier.templates import (
    SYSTEM_TYPE_TO_WD_TEMPLATE,
    TemplateMatchError,
    TemplateVerificationRequired,
    resolve_wd_template,
)


class TemplateMatcherTests(unittest.TestCase):
    def test_mapping_covers_every_canonical_type(self):
        self.assertEqual(len(SYSTEM_TYPE_TO_WD_TEMPLATE), 42)
        self.assertEqual(len(set(SYSTEM_TYPE_TO_WD_TEMPLATE.values())), 31)
        self.assertTrue(all(SYSTEM_TYPE_TO_WD_TEMPLATE.values()))

    def test_classified_decision_resolves_template(self):
        decision = ClassificationDecision(
            DecisionStatus.CLASSIFIED,
            "ETCH SYM3 AP (XA)",
        )
        self.assertEqual(resolve_wd_template(decision), "SGP_TEMPLATE_AMAT_SYM3")

    def test_verification_required_blocks_unverified_proposal(self):
        decision = ClassificationDecision(
            DecisionStatus.VERIFICATION_REQUIRED,
            "ETCH NEXTGEN 2 CHAMBER",
        )
        with self.assertRaises(TemplateVerificationRequired):
            resolve_wd_template(decision)
        self.assertEqual(
            resolve_wd_template(decision, user_verified=True),
            "SGP_TEMPLATE_AMAT_NEXTGEN_2",
        )

    def test_review_decision_cannot_resolve_template(self):
        decision = ClassificationDecision(DecisionStatus.NEEDS_REVIEW, "NEEDS REVIEW")
        with self.assertRaises(TemplateMatchError):
            resolve_wd_template(decision)

    def test_unmapped_type_cannot_resolve_template(self):
        decision = ClassificationDecision(DecisionStatus.CLASSIFIED, "UNKNOWN TYPE")
        with self.assertRaises(TemplateMatchError):
            resolve_wd_template(decision)


if __name__ == "__main__":
    unittest.main()
