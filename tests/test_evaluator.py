import threading
import time
import unittest

from system_type_identifier.classifier import SystemTypeClassifier
from system_type_identifier.evaluator import BatchEvaluator, DEFAULT_AGILE_WORKERS
from system_type_identifier.models import BomItem, BomSnapshot, LabeledExample


class _ConcurrentFakeAgileClient:
    def __init__(self):
        self.lock = threading.Lock()
        self.active = 0
        self.maximum_active = 0

    def fetch_bom(self, root_part_number, max_depth, progress, cancel_event):
        with self.lock:
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
        try:
            time.sleep(0.03)
            return BomSnapshot(
                root_part_number=root_part_number,
                items=(
                    BomItem(
                        root_part_number,
                        "0246-10000",
                        "KIT EPI PRIME",
                        "Phantom",
                        1.0,
                        1,
                    ),
                ),
                complete=True,
                requested_depth=max_depth,
            )
        finally:
            with self.lock:
                self.active -= 1


class _NextgenOneChamberFakeClient:
    def fetch_bom(self, root_part_number, max_depth, progress, cancel_event):
        return BomSnapshot(
            root_part_number=root_part_number,
            items=(
                BomItem(
                    root_part_number,
                    "0250-ONE",
                    "DOC, GAS PANEL CONFIG, 7/7 GPA, ETCH NGGP",
                    "Document",
                    1.0,
                    1,
                ),
            ),
            complete=True,
            requested_depth=max_depth,
        )


class BatchEvaluatorConcurrencyTests(unittest.TestCase):
    def test_fixed_ten_worker_pool_preserves_input_order(self):
        client = _ConcurrentFakeAgileClient()
        examples = [
            LabeledExample(
                source_row=index + 1,
                system_number=f"{700000 + index}-ES1-GPA",
                expected_system_type="EPI JOPLIN/HENDRIX",
            )
            for index in range(20)
        ]
        evaluator = BatchEvaluator(SystemTypeClassifier(), client)
        summary = evaluator.evaluate(examples)

        self.assertEqual(DEFAULT_AGILE_WORKERS, 10)
        self.assertEqual(client.maximum_active, 10)
        self.assertEqual(
            [record.system_number for record in summary.records],
            [example.system_number for example in examples],
        )
        self.assertEqual(summary.counts, {"MATCH": 20})

    def test_verification_required_is_not_counted_as_match(self):
        evaluator = BatchEvaluator(
            SystemTypeClassifier(),
            _NextgenOneChamberFakeClient(),
        )
        summary = evaluator.evaluate(
            [
                LabeledExample(
                    1,
                    "710001-XP-GP",
                    "ETCH NEXTGEN 1 CHAMBER",
                )
            ]
        )
        record = summary.records[0]
        self.assertEqual(record.evaluation_status, "VERIFICATION_REQUIRED")
        self.assertEqual(record.predicted_system_type, "ETCH NEXTGEN 1 CHAMBER")
        self.assertEqual(summary.counts, {"VERIFICATION_REQUIRED": 1})


if __name__ == "__main__":
    unittest.main()
