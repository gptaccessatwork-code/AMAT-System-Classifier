from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import threading

from .agile import AgileBomClient
from .classifier import SystemTypeClassifier
from .config import AppSettings
from .models import (
    ClassificationDecision,
    DecisionStatus,
    SystemClassification,
    SystemNumberInput,
)
from .parser import parse_system_number
from .processor import BatchSystemClassifier
from .templates import SYSTEM_TYPE_TO_WD_TEMPLATE
from .workflows import (
    WorkbookLayout,
    WorkflowMode,
    load_quote_request_layout,
    load_template_input_layout,
)


ProgressHandler = Callable[[str], None]


@dataclass(frozen=True)
class DisplayResult:
    classification: SystemClassification
    system_type: str
    wd_template: str


class SystemMatcherService:
    """UI-independent orchestration for single and workbook classifications."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.classifier = SystemTypeClassifier()
        self.agile_client: AgileBomClient | None = None

    @property
    def signed_in(self) -> bool:
        return self.agile_client is not None

    def sign_in(self, username: str, password: str) -> None:
        """Create an in-memory Agile session for this browser workspace."""

        self.sign_out()
        self.agile_client = AgileBomClient(
            username,
            password,
            wsdl_url=self.settings.wsdl_url,
        )

    def sign_out(self) -> None:
        if self.agile_client is not None:
            self.agile_client.close()
            self.agile_client = None

    def load_layout(self, path: str | Path, mode: WorkflowMode) -> WorkbookLayout:
        if mode == WorkflowMode.SYSTEM_TYPE:
            return load_quote_request_layout(path)
        return load_template_input_layout(path)

    def classify_one(
        self,
        system_number: str,
        *,
        progress: ProgressHandler | None = None,
        cancel_event: threading.Event | None = None,
    ) -> SystemClassification:
        results = self.classify_inputs(
            [SystemNumberInput(1, system_number)],
            progress=progress,
            cancel_event=cancel_event,
        )
        if not results:
            raise RuntimeError("Classification was cancelled before a result was produced")
        return results[0]

    def classify_inputs(
        self,
        inputs: list[SystemNumberInput] | tuple[SystemNumberInput, ...],
        *,
        progress: ProgressHandler | None = None,
        cancel_event: threading.Event | None = None,
    ) -> list[SystemClassification]:
        if self._requires_agile(inputs):
            if self.agile_client is None:
                raise RuntimeError("Sign in to Agile before processing this system")
            if progress:
                progress("Using your secure Agile session")
        processor = BatchSystemClassifier(
            self.classifier,
            self.agile_client,
            max_workers=self.settings.max_workers,
        )
        return processor.classify(inputs, progress=progress, cancel_event=cancel_event)

    def _requires_agile(
        self,
        inputs: list[SystemNumberInput] | tuple[SystemNumberInput, ...],
    ) -> bool:
        return any(
            self.classifier.required_bom_depth(parse_system_number(item.system_number)) != 0
            for item in inputs
        )


def display_result(classification: SystemClassification) -> DisplayResult:
    decision = classification.decision
    system_type = decision.predicted_system_type if decision.status in {
        DecisionStatus.CLASSIFIED,
        DecisionStatus.VERIFICATION_REQUIRED,
    } else ""
    template = decision.suggested_wd_template
    if not template and system_type:
        template = SYSTEM_TYPE_TO_WD_TEMPLATE.get(system_type, "")
    return DisplayResult(classification, system_type, template)


def result_row(classification: SystemClassification, mode: WorkflowMode) -> dict[str, str | int]:
    result = display_result(classification)
    decision: ClassificationDecision = classification.decision
    return {
        "row": classification.source_row,
        "system_number": classification.system_number,
        "build_type": classification.build_type or "—",
        "status": decision.status.value.replace("_", " ").title(),
        "system_type": result.system_type or "—",
        "wd_template": result.wd_template or "—",
        "rules": "; ".join(decision.rule_ids) or "—",
        "mode": mode.value,
    }
