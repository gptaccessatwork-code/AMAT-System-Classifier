from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from typing import Iterable

from .agile import AgileBomClient
from .classifier import SystemTypeClassifier
from .models import (
    BomSnapshot,
    ProgressCallback,
    SystemClassification,
    SystemNumberInput,
)
from .parser import parse_system_number


DEFAULT_AGILE_WORKERS = 10


class BatchSystemClassifier:
    def __init__(
        self,
        classifier: SystemTypeClassifier,
        agile_client: AgileBomClient | None,
        max_workers: int = DEFAULT_AGILE_WORKERS,
    ) -> None:
        self.classifier = classifier
        self.agile_client = agile_client
        self.max_workers = max(1, max_workers)

    def classify(
        self,
        inputs: Iterable[SystemNumberInput],
        progress: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> list[SystemClassification]:
        inputs = list(inputs)
        results: list[SystemClassification | None] = [None] * len(inputs)
        if progress:
            progress(
                f"Classifying {len(inputs)} systems with "
                f"{self.max_workers} Agile workers"
            )

        with ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="agile-classify",
        ) as executor:
            futures = {
                executor.submit(self._classify_one, item, cancel_event): index
                for index, item in enumerate(inputs)
            }
            completed = 0
            for future in as_completed(futures):
                index = futures[future]
                if cancel_event is not None and cancel_event.is_set():
                    for pending in futures:
                        pending.cancel()
                    break
                results[index] = future.result()
                completed += 1
                if progress:
                    progress(
                        f"Completed {completed}/{len(inputs)}: "
                        f"{inputs[index].system_number}"
                    )

        return [result for result in results if result is not None]

    def _classify_one(
        self,
        item: SystemNumberInput,
        cancel_event: threading.Event | None,
    ) -> SystemClassification:
        parsed = parse_system_number(item.system_number)
        depth = self.classifier.required_bom_depth(parsed)
        bom = None
        if depth != 0 and parsed.valid:
            if self.agile_client is not None:
                bom = self.agile_client.fetch_bom(
                    parsed.normalized,
                    max_depth=depth,
                    progress=None,
                    cancel_event=cancel_event,
                )
            else:
                bom = BomSnapshot(
                    root_part_number=parsed.normalized,
                    items=(),
                    complete=False,
                    requested_depth=depth,
                    errors=("Agile client is unavailable",),
                )
        decision = self.classifier.classify(parsed, bom)
        return SystemClassification(
            source_row=item.source_row,
            system_number=parsed.normalized or item.system_number,
            build_type="" if parsed.build_type is None else parsed.build_type.value,
            decision=decision,
        )
