from __future__ import annotations

import threading
from typing import Iterable

from .agile import AgileBomClient
from .classifier import SystemTypeClassifier
from .models import (
    DecisionStatus,
    EvaluationRecord,
    EvaluationSummary,
    LabeledExample,
    ProgressCallback,
    SystemNumberInput,
)
from .processor import BatchSystemClassifier, DEFAULT_AGILE_WORKERS


class BatchEvaluator:
    def __init__(
        self,
        classifier: SystemTypeClassifier,
        agile_client: AgileBomClient | None,
        max_workers: int = DEFAULT_AGILE_WORKERS,
    ) -> None:
        self.classifier = classifier
        self.agile_client = agile_client
        self.max_workers = max(1, max_workers)

    def evaluate(
        self,
        examples: Iterable[LabeledExample],
        progress: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> EvaluationSummary:
        examples = list(examples)
        inputs = [
            SystemNumberInput(example.source_row, example.system_number)
            for example in examples
        ]
        classifications = BatchSystemClassifier(
            self.classifier,
            self.agile_client,
            self.max_workers,
        ).classify(inputs, progress=progress, cancel_event=cancel_event)
        expected_by_row = {
            example.source_row: example.expected_system_type for example in examples
        }
        records = [
            self._to_evaluation_record(
                classification,
                expected_by_row[classification.source_row],
            )
            for classification in classifications
        ]
        return EvaluationSummary(records)

    @staticmethod
    def _to_evaluation_record(classification, expected_system_type: str) -> EvaluationRecord:
        decision = classification.decision
        if decision.status == DecisionStatus.CLASSIFIED:
            evaluation_status = (
                "MATCH"
                if decision.predicted_system_type.strip().upper()
                == expected_system_type.strip().upper()
                else "MISMATCH"
            )
        else:
            evaluation_status = decision.status.value
        return EvaluationRecord(
            source_row=classification.source_row,
            system_number=classification.system_number,
            expected_system_type=expected_system_type,
            predicted_system_type=decision.predicted_system_type,
            evaluation_status=evaluation_status,
            build_type=classification.build_type,
            rule_ids="; ".join(decision.rule_ids),
            evidence="\n".join(decision.evidence),
            warnings="\n".join(decision.warnings),
        )
