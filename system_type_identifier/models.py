from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Callable


class BuildType(StrEnum):
    NORMAL = "NORMAL"
    NSO = "NSO"


class DecisionStatus(StrEnum):
    CLASSIFIED = "CLASSIFIED"
    VERIFICATION_REQUIRED = "VERIFICATION_REQUIRED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    UNCLASSIFIED = "UNCLASSIFIED"
    EXCLUDED_INVALID_FORMAT = "EXCLUDED_INVALID_FORMAT"
    MANUAL_REVIEW_NSO = "MANUAL_REVIEW_NSO"
    BOM_RETRIEVAL_ERROR = "BOM_RETRIEVAL_ERROR"
    RULE_CONFLICT = "RULE_CONFLICT"


@dataclass(frozen=True)
class ParsedSystemNumber:
    original: str
    normalized: str
    valid: bool
    errors: tuple[str, ...] = ()
    slot_number: str = ""
    base_slot_number: str = ""
    build_type: BuildType | None = None
    nso_suffix: str | None = None
    nso_marker: str | None = None
    nso_sequence: str | None = None
    product_family: str = ""
    chamber: str = ""


@dataclass(frozen=True)
class BomItem:
    parent_part_number: str
    part_number: str
    description: str
    category: str
    local_quantity: float
    depth: int
    path: tuple[str, ...] = ()


@dataclass(frozen=True)
class BomSnapshot:
    root_part_number: str
    items: tuple[BomItem, ...]
    complete: bool
    requested_depth: int | None
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def children_of(self, part_number: str) -> tuple[BomItem, ...]:
        target = part_number.strip().upper()
        return tuple(
            item
            for item in self.items
            if item.parent_part_number.strip().upper() == target
        )


@dataclass(frozen=True)
class ClassificationDecision:
    status: DecisionStatus
    predicted_system_type: str = ""
    rule_ids: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class LabeledExample:
    source_row: int
    system_number: str
    expected_system_type: str


@dataclass(frozen=True)
class SystemNumberInput:
    source_row: int
    system_number: str


@dataclass(frozen=True)
class SystemClassification:
    source_row: int
    system_number: str
    build_type: str
    decision: ClassificationDecision


@dataclass(frozen=True)
class EvaluationRecord:
    source_row: int
    system_number: str
    expected_system_type: str
    predicted_system_type: str
    evaluation_status: str
    build_type: str
    rule_ids: str
    evidence: str
    warnings: str


ProgressCallback = Callable[[str], None]


@dataclass
class EvaluationSummary:
    records: list[EvaluationRecord] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for record in self.records:
            result[record.evaluation_status] = result.get(record.evaluation_status, 0) + 1
        return result
