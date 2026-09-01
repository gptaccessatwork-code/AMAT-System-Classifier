from __future__ import annotations

import re

from .models import BuildType, ParsedSystemNumber


_NORMAL_SLOT = re.compile(r"^[A-Z0-9]{6}$")
_NSO_SLOT = re.compile(
    r"^(?P<base>[A-Z0-9]{6})(?P<marker>[A-Z])(?P<sequence>[0-9]{1,2})$"
)
_SEGMENT = re.compile(r"^[A-Z0-9]+$")


def parse_system_number(value: object) -> ParsedSystemNumber:
    original = "" if value is None else str(value)
    normalized = original.strip().upper()
    parts = normalized.split("-")
    errors: list[str] = []

    if len(parts) != 3:
        errors.append("System number must contain exactly three hyphen-separated segments")
        return ParsedSystemNumber(original, normalized, False, tuple(errors))

    slot, family, chamber = parts
    if not family or not _SEGMENT.fullmatch(family):
        errors.append("Product family must be a nonempty alphanumeric segment")
    if not chamber or not _SEGMENT.fullmatch(chamber):
        errors.append("Chamber must be a nonempty alphanumeric segment")

    normal_match = _NORMAL_SLOT.fullmatch(slot)
    nso_match = _NSO_SLOT.fullmatch(slot)
    if normal_match:
        build_type = BuildType.NORMAL
        base = slot
        suffix = marker = sequence = None
    elif nso_match:
        build_type = BuildType.NSO
        base = nso_match.group("base")
        marker = nso_match.group("marker")
        sequence = nso_match.group("sequence")
        suffix = f"{marker}{sequence}"
    else:
        build_type = None
        base = ""
        suffix = marker = sequence = None
        errors.append(
            "Slot must be six alphanumeric characters, optionally followed "
            "by one letter and one or two NSO digits"
        )

    return ParsedSystemNumber(
        original=original,
        normalized=normalized,
        valid=not errors,
        errors=tuple(errors),
        slot_number=slot,
        base_slot_number=base,
        build_type=build_type,
        nso_suffix=suffix,
        nso_marker=marker,
        nso_sequence=sequence,
        product_family=family,
        chamber=chamber,
    )
