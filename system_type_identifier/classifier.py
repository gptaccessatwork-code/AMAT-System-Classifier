from __future__ import annotations

import re
from typing import Iterable

from .models import (
    BomItem,
    BomSnapshot,
    BuildType,
    ClassificationDecision,
    DecisionStatus,
    ParsedSystemNumber,
)


RULESET_VERSION = "2026.08.28.1"

VERIFICATION_REQUIRED_TYPES = frozenset(
    {
        "DSM PRODUCER SE 2 CHAMBER",
        "DSM PRODUCER SE 2 CHAMBER WITH GPLIS",
        "DSM PRODUCER SE 3 CHAMBER",
        "DSM PRODUCER SE 3 CHAMBER WITH GPLIS",
        "ETCH NEXTGEN 1 CHAMBER",
        "ETCH NEXTGEN 2 CHAMBER",
    }
)

_LDS = re.compile(r"(?<![A-Z0-9])LDS(?![A-Z0-9])", re.IGNORECASE)
_RETROFIT = re.compile(r"(?<![A-Z0-9])RETROFIT(?![A-Z0-9])", re.IGNORECASE)
_GPLS = re.compile(r"(?<![A-Z0-9])GPLS[A-C]?(?![A-Z0-9])", re.IGNORECASE)
_GP_SINGLE = re.compile(r"^GP[A-Z]$")
_POSITION_NAMES = ("POSITION ONE", "POSITION TWO", "POSITION THREE")
_OZONATOR_TYPES = (
    "ASSY, OZONATOR WITH CHAMBER A, PRODUCER SE",
    "ASSY, OZONATOR WITH CHAMBER B, PRODUCER SE",
    "ASSY, OZONATOR WITH CHAMBER C, PRODUCER SE",
    "ASSY, OZONATOR WITH CHAMBER A & C, PRODUCER SE",
    "ASSY, OZONATOR WITH CHAMBER B & C, PRODUCER SE",
    "ASSY, OZONATOR WITH CHAMBER A & B, PRODUCER SE",
    "ASSY, OZONATOR WITH CHAMBER A & B & C, PRODUCER SE",
)


class SystemTypeClassifier:
    def required_bom_depth(self, parsed: ParsedSystemNumber) -> int | None:
        if not parsed.valid:
            return 0
        if parsed.build_type == BuildType.NSO:
            return None
        family, chamber = parsed.product_family, parsed.chamber
        if chamber in {"SLD", "GPLL"}:
            return 0
        if chamber in {"INOZ", "INZC"}:
            return 2
        if family == "DF" and "UV" in chamber:
            return 0
        if family in {"XA3", "XA3T"} and chamber in {"GPA", "GPB", "GPC"}:
            return 0
        if family in {"EY1", "EY2", "EY4", "DA", "XXT"}:
            return 0
        if family in {"DG", "DX"} and chamber != "GP" and not _GP_SINGLE.fullmatch(chamber):
            return 0
        return 2

    def classify(
        self,
        parsed: ParsedSystemNumber,
        bom: BomSnapshot | None = None,
    ) -> ClassificationDecision:
        if not parsed.valid:
            return ClassificationDecision(
                DecisionStatus.EXCLUDED_INVALID_FORMAT,
                evidence=parsed.errors,
            )

        gate_evidence: list[str] = []
        if parsed.build_type == BuildType.NSO:
            if bom is None:
                return self._bom_error("NSO full-build gate requires a recursive BOM")
            retrofit = next(
                (
                    item
                    for item in bom.items
                    if item.category.strip().lower() == "document"
                    and _RETROFIT.search(item.description)
                ),
                None,
            )
            if retrofit is not None:
                return ClassificationDecision(
                    DecisionStatus.MANUAL_REVIEW_NSO,
                    predicted_system_type="NSO",
                    rule_ids=("NSO-RETROFIT-NON-FULL-BUILD",),
                    evidence=(
                        f"Retrofit document {retrofit.part_number} at level "
                        f"{retrofit.depth}: {retrofit.description}",
                    ),
                )
            if parsed.chamber in {"INOZ", "INZC"}:
                inoz_decision = self._classify_inoz(bom)
                if inoz_decision.status == DecisionStatus.CLASSIFIED:
                    return ClassificationDecision(
                        status=inoz_decision.status,
                        predicted_system_type=inoz_decision.predicted_system_type,
                        rule_ids=("NSO-FULL-BUILD-INOZ-EVIDENCE",) + inoz_decision.rule_ids,
                        evidence=(
                            "Explicit INOZ position/Ozonator BOM evidence establishes a full build",
                        )
                        + inoz_decision.evidence,
                        warnings=inoz_decision.warnings,
                    )
            enclosure = next(
                (item for item in bom.items if "ENCLOSURE" in item.description.upper()),
                None,
            )
            if enclosure is None:
                if not bom.complete:
                    return self._bom_error(
                        "Recursive NSO BOM was incomplete; ENCLOSURE absence is not established",
                        bom,
                    )
                return ClassificationDecision(
                    DecisionStatus.MANUAL_REVIEW_NSO,
                    predicted_system_type="NSO",
                    rule_ids=("NSO-NON-FULL-BUILD",),
                    evidence=(
                        f"No ENCLOSURE match across {len(bom.items)} retrieved BOM rows",
                    ),
                    warnings=(
                        "BOM size is recorded as an indication only; the count rule is unresolved",
                    ),
                )
            gate_evidence.append(
                f"Full-build NSO: {enclosure.part_number} at level {enclosure.depth} "
                f"contains ENCLOSURE in its description"
            )

        decision = self._classify_eligible(parsed, bom)
        if gate_evidence:
            decision = ClassificationDecision(
                status=decision.status,
                predicted_system_type=decision.predicted_system_type,
                rule_ids=("NSO-FULL-BUILD",) + decision.rule_ids,
                evidence=tuple(gate_evidence) + decision.evidence,
                warnings=decision.warnings,
            )
        return self._require_user_verification(decision)

    def _classify_eligible(
        self,
        parsed: ParsedSystemNumber,
        bom: BomSnapshot | None,
    ) -> ClassificationDecision:
        family, chamber = parsed.product_family, parsed.chamber

        if chamber == "SLD":
            return self._classified("ETCH SLD BOX", "SYS-CHAMBER-SLD", "Chamber is SLD")
        if chamber == "GPLL":
            return self._classified(
                "ETCH LOAD LOCK (GPLL)", "SYS-CHAMBER-GPLL", "Chamber is GPLL"
            )
        if chamber in {"INOZ", "INZC"}:
            return self._classify_inoz(bom)
        if family == "DF" and "UV" in chamber:
            return self._classified(
                "DSM PRODUCER SE UV CHAMBER",
                "SYS-DF-UV",
                f"Family DF and chamber {chamber} contains UV",
            )
        if family in {"XA3", "XA3T"} and chamber in {"GPA", "GPB", "GPC"}:
            return self._classified(
                "ETCH SYM3 AP (XA)",
                "SYS-XA3-XA3T-GPABC",
                f"Family {family} with chamber {chamber}",
            )
        if family in {"EY1", "EY2"}:
            return self._classified(
                "EPI SINGLE CLUSTER", "SYS-EY1-EY2", f"Product family is {family}"
            )
        if family == "EY4":
            return self._classified("EPI ERMIAS", "SYS-EY4", "Product family is EY4")
        if family == "DA":
            return self._classified(
                "DSM HDP CENTURA AP (DA)", "SYS-DA", "Product family is DA"
            )
        if family == "XXT":
            return self._classified("ETCH NAPA (XX)", "SYS-XXT", "Product family is XXT")
        if family == "DF":
            return self._classify_producer_se(parsed, bom)
        if family == "DG":
            return self._classify_gplis_family(parsed, bom, "DSM PRODUCER GT")
        if family == "DX":
            return self._classify_gplis_family(parsed, bom, "DSM APACHE (DX)")
        if family == "TY":
            return self._classify_radiance(bom)
        if family in {"EY3", "ES1"}:
            return self._classify_joplin(parsed, bom)
        if family == "PJ":
            return self._classify_pj(bom)

        nextgen = self._classify_nextgen(bom)
        if nextgen.status != DecisionStatus.UNCLASSIFIED:
            return nextgen
        return ClassificationDecision(
            DecisionStatus.UNCLASSIFIED,
            evidence=(f"No rule matched product family {family} and chamber {chamber}",),
        )

    def _classify_producer_se(
        self, parsed: ParsedSystemNumber, bom: BomSnapshot | None
    ) -> ClassificationDecision:
        if bom is None:
            return self._bom_error("Producer SE classification requires a BOM")
        chamber = parsed.chamber
        if _GP_SINGLE.fullmatch(chamber):
            found, evidence = self._direct_gplis(bom, parsed.normalized)
            if found is None:
                return self._bom_error("Producer SE BOM was incomplete", bom)
            output = "DSM PRODUCER SE 1 CHAMBER" + (" WITH GPLIS" if found else "")
            return self._classified(output, "BOM-DF-ONE-CHAMBER", *evidence)
        if chamber != "GP":
            return ClassificationDecision(
                DecisionStatus.UNCLASSIFIED,
                evidence=(f"DF chamber {chamber} is not a recognized Producer SE form",),
            )

        children = self._matching_chamber_children(parsed, bom)
        chambers = {item.part_number.rsplit("-", 1)[-1] for item in children}
        if chambers == {"GPA", "GPB", "GPC"}:
            count = 3
        elif len(chambers) == 2 and chambers <= {"GPA", "GPB", "GPC"}:
            count = 2
        elif (
            parsed.build_type == BuildType.NSO
            and len(chambers) == 1
            and chambers <= {"GPA", "GPB", "GPC"}
        ):
            count = 1
        else:
            return ClassificationDecision(
                DecisionStatus.UNCLASSIFIED,
                rule_ids=("BOM-DF-GP-CHAMBER-COUNT",),
                evidence=(f"Found chamber children: {', '.join(sorted(chambers)) or 'none'}",),
            )

        found, evidence = self._hierarchical_gplis(parsed, bom, children)
        if found is None:
            return self._bom_error("Producer SE multi-chamber BOM was incomplete", bom)
        output = f"DSM PRODUCER SE {count} CHAMBER" + (" WITH GPLIS" if found else "")
        return self._classified(
            output,
            "BOM-DF-GP-CHAMBER-COUNT",
            f"Distinct chamber children: {', '.join(sorted(chambers))}",
            *evidence,
        )

    def _classify_gplis_family(
        self,
        parsed: ParsedSystemNumber,
        bom: BomSnapshot | None,
        base_output: str,
    ) -> ClassificationDecision:
        if parsed.chamber != "GP" and not _GP_SINGLE.fullmatch(parsed.chamber):
            return ClassificationDecision(
                DecisionStatus.NEEDS_REVIEW,
                predicted_system_type="NEEDS REVIEW",
                rule_ids=("SYS-UNRECOGNIZED-GPLIS-CHAMBER",),
                evidence=(
                    f"{parsed.product_family} chamber {parsed.chamber} is not a recognized "
                    "GP or single-letter GP chamber form",
                ),
            )
        if bom is None:
            return self._bom_error(f"{base_output} classification requires a BOM")
        if parsed.chamber == "GP":
            children = self._matching_chamber_children(parsed, bom)
            found, evidence = self._hierarchical_gplis(parsed, bom, children)
        else:
            found, evidence = self._direct_gplis(bom, parsed.normalized)
        if found is None:
            return self._bom_error(f"{base_output} BOM was incomplete", bom)
        output = base_output + (" WITH GPLIS" if found else "")
        return self._classified(output, "BOM-GPLIS-SHARED", *evidence)

    def _direct_gplis(
        self, bom: BomSnapshot, parent_part_number: str
    ) -> tuple[bool | None, tuple[str, ...]]:
        matches = [
            item
            for item in bom.children_of(parent_part_number)
            if _is_gplis_description(item.description)
        ]
        if matches:
            item = matches[0]
            return True, (f"{item.part_number}: {item.description}",)
        if not bom.complete:
            return None, ()
        return False, ("No GPLS, F404M, or schematic 1-LIQ/2-LIQ/3-LIQ match in the direct BOM",)

    def _hierarchical_gplis(
        self,
        parsed: ParsedSystemNumber,
        bom: BomSnapshot,
        chamber_children: Iterable[BomItem],
    ) -> tuple[bool | None, tuple[str, ...]]:
        parent_match = next(
            (
                item
                for item in bom.children_of(parsed.normalized)
                if _is_gplis_description(item.description)
            ),
            None,
        )
        if parent_match:
            return True, (f"Parent match {parent_match.part_number}: {parent_match.description}",)
        for child in chamber_children:
            match = next(
                (
                    item
                    for item in bom.children_of(child.part_number)
                    if _is_gplis_description(item.description)
                ),
                None,
            )
            if match:
                return True, (
                    f"Child {child.part_number} match {match.part_number}: {match.description}",
                )
        if not bom.complete:
            return None, ()
        return False, (
            "No GPLS, F404M, or schematic 1-LIQ/2-LIQ/3-LIQ match in parent or chamber-child BOMs",
        )

    @staticmethod
    def _matching_chamber_children(
        parsed: ParsedSystemNumber, bom: BomSnapshot
    ) -> tuple[BomItem, ...]:
        prefix = f"{parsed.slot_number}-{parsed.product_family}-"
        return tuple(
            item
            for item in bom.children_of(parsed.normalized)
            if item.part_number.startswith(prefix)
            and item.part_number.rsplit("-", 1)[-1] in {"GPA", "GPB", "GPC"}
        )

    def _classify_radiance(self, bom: BomSnapshot | None) -> ClassificationDecision:
        if bom is None:
            return self._bom_error("Radiance classification requires a BOM")
        direct = bom.children_of(bom.root_part_number)
        dpn = next((item for item in direct if "DPN" in item.description.upper()), None)
        if dpn:
            return self._classified(
                "FEP RADIANCE DPN CHAMBER", "BOM-TY-DPN", f"{dpn.part_number}: {dpn.description}"
            )
        radiance = next(
            (item for item in direct if "RADIANCE" in item.description.upper()), None
        )
        if radiance:
            return self._classified(
                "FEP RADIANCE 1 CHAMBER",
                "BOM-TY-RADIANCE",
                f"{radiance.part_number}: {radiance.description}",
            )
        if not bom.complete:
            return self._bom_error("Radiance BOM was incomplete", bom)
        return ClassificationDecision(
            DecisionStatus.UNCLASSIFIED,
            evidence=("No DPN or RADIANCE match in direct BOM descriptions",),
        )

    def _classify_joplin(
        self, parsed: ParsedSystemNumber, bom: BomSnapshot | None
    ) -> ClassificationDecision:
        if bom is None:
            return self._bom_error("JOPLIN/HENDRIX classification requires a BOM")
        direct = bom.children_of(parsed.normalized)
        applicable = direct
        nesting_evidence: tuple[str, ...] = ()
        if parsed.product_family == "EY3" and len(direct) == 1:
            holder = direct[0]
            applicable = bom.children_of(holder.part_number)
            nesting_evidence = (f"EY3 holder BOM resolved through {holder.part_number}",)
        match = next((item for item in applicable if _is_positive_lds_kit(item)), None)
        if match:
            return self._classified(
                "EPI JOPLIN/HENDRIX WITH LDM",
                "BOM-JOPLIN-LDS",
                *nesting_evidence,
                f"{match.part_number}: {match.description}",
            )
        if not bom.complete:
            return self._bom_error("JOPLIN/HENDRIX BOM was incomplete", bom)
        return self._classified(
            "EPI JOPLIN/HENDRIX",
            "BOM-JOPLIN-NO-LDS",
            *nesting_evidence,
            "No positive non-document KIT ... LDS item in the applicable main BOM",
        )

    def _classify_pj(self, bom: BomSnapshot | None) -> ClassificationDecision:
        if bom is None:
            return self._bom_error("PJ classification requires a two-level BOM")
        descriptions = [(item, _normalize_text(item.description)) for item in bom.items if item.depth <= 2]
        txz = [item for item, text in descriptions if "TXZ" in text]
        ald = [
            item
            for item, text in descriptions
            if any(term in text for term in ("ALD TAN", "ALD2 TAN", "ALD TAN II"))
        ]
        if txz and ald:
            return ClassificationDecision(
                DecisionStatus.RULE_CONFLICT,
                rule_ids=("BOM-PJ-CONFLICT",),
                evidence=(
                    f"TXZ match: {txz[0].part_number}: {txz[0].description}",
                    f"ALD match: {ald[0].part_number}: {ald[0].description}",
                ),
            )
        if txz:
            return self._classified("TXZ", "BOM-PJ-TXZ", f"{txz[0].part_number}: {txz[0].description}")
        if ald:
            return self._classified(
                "ALD 2 TAN", "BOM-PJ-ALD-TAN", f"{ald[0].part_number}: {ald[0].description}"
            )
        if not bom.complete:
            return self._bom_error("PJ two-level BOM was incomplete", bom)
        return self._classified(
            "SICONI", "BOM-PJ-FALLBACK-SICONI", "No TXZ or ALD TaN indicator at levels 1-2"
        )

    def _classify_inoz(self, bom: BomSnapshot | None) -> ClassificationDecision:
        if bom is None:
            return self._bom_error("INOZ classification requires a two-level BOM")
        scoped = [item for item in bom.items if item.depth <= 2]
        normalized = [(item, _normalize_text(item.description)) for item in scoped]
        explicit: list[tuple[str, BomItem]] = []
        for canonical in _OZONATOR_TYPES:
            needle = _normalize_text(canonical)
            explicit.extend((canonical, item) for item, text in normalized if needle in text)
        distinct = {canonical for canonical, _ in explicit}
        if len(distinct) > 1:
            return ClassificationDecision(
                DecisionStatus.RULE_CONFLICT,
                rule_ids=("BOM-INOZ-OZONATOR-CONFLICT",),
                evidence=tuple(sorted(distinct)),
            )
        if distinct:
            output = next(iter(distinct))
            item = next(item for canonical, item in explicit if canonical == output)
            return self._classified(output, "BOM-INOZ-EXPLICIT-OZONATOR", f"{item.part_number}: {item.description}")

        positions = {
            phrase
            for _, text in normalized
            for phrase in _POSITION_NAMES
            if phrase in text
        }
        count = len(positions)
        if count not in {1, 2, 3}:
            if not bom.complete:
                return self._bom_error("INOZ BOM was incomplete", bom)
            return ClassificationDecision(
                DecisionStatus.UNCLASSIFIED,
                rule_ids=("BOM-INOZ-POSITIONS",),
                evidence=(f"Position set: {', '.join(sorted(positions)) or 'none'}",),
            )
        samsung = next((item for item, text in normalized if "SAMSUNG" in text), None)
        output = f"CONFIGURED INOZ, {count} CHAMBER, PRODUCER SE/GT SACVD"
        if samsung:
            output += " SAMSUNG"
        evidence = [f"Positions: {', '.join(sorted(positions))}"]
        if samsung:
            evidence.append(f"Samsung match {samsung.part_number}: {samsung.description}")
        return self._classified(output, "BOM-INOZ-POSITIONS", *evidence)

    def _classify_nextgen(self, bom: BomSnapshot | None) -> ClassificationDecision:
        if bom is None:
            return ClassificationDecision(DecisionStatus.UNCLASSIFIED)
        explicit_candidates: list[tuple[int, str]] = []
        pallet_chambers: set[str] = set()
        for item in (row for row in bom.items if row.depth <= 2):
            text = _normalize_text(item.description)
            contextual = any(token in text for token in ("DOC", "PALLET", "GP CORE", "NGGP"))
            if not contextual:
                continue
            explicit = re.search(r"(?<![A-Z0-9])([1-4])-CH(?![A-Z0-9])", text)
            if explicit:
                explicit_candidates.append((int(explicit.group(1)), f"{item.part_number}: {item.description}"))
            split_ab_cd = (
                re.search(r"(?:^|[-\s])AB(?:\s|,|$)", text) is not None
                and re.search(r"(?:^|[-\s])CD(?:\s|,|$)", text) is not None
            )
            compact = re.search(r"(?:PALLET|PAL)\s+(ABCD|ABC|AB)(?![A-Z])", text)
            if compact and not split_ab_cd:
                explicit_candidates.append((len(compact.group(1)), f"{item.part_number}: {item.description}"))
            if "DOC" in text:
                doc_compact = re.search(r"(?<![A-Z])(ABCD|ABC)(?![A-Z])", text)
                if doc_compact:
                    explicit_candidates.append(
                        (len(doc_compact.group(1)), f"{item.part_number}: {item.description}")
                    )
            if "A&B" in text and "C&D" in text:
                explicit_candidates.append((4, f"{item.part_number}: {item.description}"))
            elif split_ab_cd:
                explicit_candidates.append((4, f"{item.part_number}: {item.description}"))
            gp = re.search(r"(?<![A-Z0-9])GP([A-D])(?![A-Z0-9])", text)
            if gp and "DOC" in text:
                explicit_candidates.append((1, f"{item.part_number}: {item.description}"))
            if "KIT" in text and "PALLET" in text:
                for grouped in re.findall(
                    r"(?<![A-Z0-9])CH[- ]([A-D](?:/[A-D]){1,3})(?![A-Z0-9])",
                    text,
                ):
                    pallet_chambers.update(grouped.split("/"))
                for chamber in re.findall(r"(?<![A-Z0-9])CH[- ]([A-D])(?![A-Z0-9])", text):
                    pallet_chambers.add(chamber)
        counts = {count for count, _ in explicit_candidates}
        if len(counts) > 1:
            return ClassificationDecision(
                DecisionStatus.RULE_CONFLICT,
                rule_ids=("BOM-NEXTGEN-COUNT-CONFLICT",),
                evidence=tuple(evidence for _, evidence in explicit_candidates),
            )
        if counts:
            count = next(iter(counts))
            evidence = [value for _, value in explicit_candidates]
            if len(pallet_chambers) == count:
                evidence.append(f"Pallet chambers: {', '.join(sorted(pallet_chambers))}")
            return self._classified(
                f"ETCH NEXTGEN {count} CHAMBER",
                "BOM-NEXTGEN-CHAMBER-COUNT",
                *evidence,
            )
        if pallet_chambers:
            count = len(pallet_chambers)
            return self._classified(
                f"ETCH NEXTGEN {count} CHAMBER",
                "BOM-NEXTGEN-PALLET-COUNT",
                f"Pallet chambers: {', '.join(sorted(pallet_chambers))}",
            )
        if not bom.complete:
            return self._bom_error("NEXTGEN candidate BOM was incomplete", bom)
        return ClassificationDecision(DecisionStatus.UNCLASSIFIED)

    @staticmethod
    def _classified(output: str, rule_id: str, *evidence: str) -> ClassificationDecision:
        return ClassificationDecision(
            DecisionStatus.CLASSIFIED,
            predicted_system_type=output,
            rule_ids=(rule_id,),
            evidence=tuple(item for item in evidence if item),
        )

    @staticmethod
    def _require_user_verification(
        decision: ClassificationDecision,
    ) -> ClassificationDecision:
        if (
            decision.status != DecisionStatus.CLASSIFIED
            or decision.predicted_system_type not in VERIFICATION_REQUIRED_TYPES
        ):
            return decision
        return ClassificationDecision(
            status=DecisionStatus.VERIFICATION_REQUIRED,
            predicted_system_type=decision.predicted_system_type,
            rule_ids=decision.rule_ids + ("HUMAN-VERIFY-LOW-CONFIDENCE-TYPE",),
            evidence=decision.evidence
            + (
                "User verification is mandatory for this coverage-limited system type",
            ),
            warnings=decision.warnings
            + (
                "Do not use this classification downstream until a user confirms it",
            ),
        )

    @staticmethod
    def _bom_error(message: str, bom: BomSnapshot | None = None) -> ClassificationDecision:
        evidence = [message]
        if bom is not None:
            evidence.extend(bom.errors)
        return ClassificationDecision(
            DecisionStatus.BOM_RETRIEVAL_ERROR,
            evidence=tuple(evidence),
            warnings=() if bom is None else bom.warnings,
        )


def _contains_any(value: str, terms: Iterable[str]) -> bool:
    upper = value.upper()
    return any(term in upper for term in terms)


def _is_gplis_description(value: str) -> bool:
    text = _normalize_text(value)
    if "F404M" in text or _GPLS.search(text):
        return True
    return "SCHEMATIC" in text and re.search(
        r"(?<![A-Z0-9])[1-3]-LIQ(?![A-Z0-9])",
        text,
    ) is not None


def _is_positive_lds_kit(item: BomItem) -> bool:
    if item.category.strip().lower() == "document":
        return False
    text = _normalize_text(item.description)
    if not re.search(r"^KIT\b.*(?<![A-Z0-9])LDS(?![A-Z0-9])", text):
        return False
    negative = re.search(
        r"(?:W/O|W/OUT|WITHOUT|NO)\b[^,;]*\bLDS\b",
        text,
    )
    return negative is None


def _normalize_text(value: str) -> str:
    return " ".join(value.upper().split())
