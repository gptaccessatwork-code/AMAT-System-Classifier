from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from .models import ClassificationDecision, DecisionStatus


TEMPLATE_MAP_VERSION = "2026.08.27.1"

SYSTEM_TYPE_TO_WD_TEMPLATE: Mapping[str, str] = MappingProxyType(
    {
        "DSM PRODUCER SE 1 CHAMBER": "SGP_AMAT_SE_1_CH",
        "DSM PRODUCER SE 1 CHAMBER WITH GPLIS": "SGP_AMAT_SE_1_CH_GPLIS",
        "DSM PRODUCER SE 2 CHAMBER": "SGP_AMAT_SE_2_CH",
        "DSM PRODUCER SE 2 CHAMBER WITH GPLIS": "SGP_AMAT_SE_2_CH_GPLIS",
        "DSM PRODUCER SE 3 CHAMBER": "SGP_AMAT_SE_3_CH",
        "DSM PRODUCER SE 3 CHAMBER WITH GPLIS": "SGP_AMAT_SE_3_CH_GPLIS",
        "DSM PRODUCER GT": "SGP_TEMPLATE_AMAT_GT",
        "DSM PRODUCER GT WITH GPLIS": "SGP_TEMPLATE_AMAT_GT_GPLIS",
        "DSM PRODUCER SE UV CHAMBER": "SGP_TEMPLATE_AMAT_SE_UV",
        "DSM HDP CENTURA AP (DA)": "SGP_TEMPLATE_HDP",
        "DSM APACHE (DX)": "SGP_TEMPLATE_AMAT_APACHE",
        "DSM APACHE (DX) WITH GPLIS": "SGP_TEMPLATE_AMAT_APACHE_GPLIS",
        "ETCH NEXTGEN 1 CHAMBER": "SGP_TEMPLATE_AMAT_NEXTGEN_1",
        "ETCH NEXTGEN 2 CHAMBER": "SGP_TEMPLATE_AMAT_NEXTGEN_2",
        "ETCH NEXTGEN 3 CHAMBER": "SGP_TEMPLATE_AMAT_NEXTGEN_3",
        "ETCH NEXTGEN 4 CHAMBER": "SGP_TEMPLATE_AMAT_NEXTGEN_4",
        "ETCH SLD BOX": "SGP_TEMPLATE_AMAT_NEXTGEN_SLD",
        "ETCH SYM3 AP (XA)": "SGP_TEMPLATE_AMAT_SYM3",
        "ETCH LOAD LOCK (GPLL)": "SGP_TEMPLATE_AMAT_GPLL",
        "ETCH NAPA (XX)": "SGP_TEMPLATE_NAPA",
        "FEP RADIANCE 1 CHAMBER": "SGP_TEMPLATE_RADIANCE",
        "FEP RADIANCE DPN CHAMBER": "SGP_TEMPLATE_DPN",
        "ALD 2 TAN": "SGP_TEMPLATE_AMAT_SICONI_OATES",
        "EPI SINGLE CLUSTER": "SGP_TEMPLATE_AMAT_EPI",
        "EPI JOPLIN/HENDRIX": "SGP_TEMPLATE_AMAT_JOPLIN",
        "EPI JOPLIN/HENDRIX WITH LDM": "SGP_TEMPLATE_AMAT_JOPLIN_LDS",
        "EPI ERMIAS": "SGP_TEMPLATE_AMAT_ERMIAS",
        "SICONI": "SGP_TEMPLATE_AMAT_SICONI_OATES",
        "TXZ": "SGP_TEMPLATE_AMAT_TXZ",
        "CONFIGURED INOZ, 1 CHAMBER, PRODUCER SE/GT SACVD": "SGP_TEMPLATE_AMAT_INZC_1",
        "CONFIGURED INOZ, 1 CHAMBER, PRODUCER SE/GT SACVD SAMSUNG": "SGP_TEMPLATE_AMAT_INZC_1",
        "CONFIGURED INOZ, 2 CHAMBER, PRODUCER SE/GT SACVD": "SGP_TEMPLATE_AMAT_INZC_2",
        "CONFIGURED INOZ, 2 CHAMBER, PRODUCER SE/GT SACVD SAMSUNG": "SGP_TEMPLATE_AMAT_INZC_2",
        "CONFIGURED INOZ, 3 CHAMBER, PRODUCER SE/GT SACVD": "SGP_TEMPLATE_AMAT_INZC_3",
        "CONFIGURED INOZ, 3 CHAMBER, PRODUCER SE/GT SACVD SAMSUNG": "SGP_TEMPLATE_AMAT_INZC_3",
        "ASSY, OZONATOR WITH CHAMBER A, PRODUCER SE": "SGP_TEMPLATE_AMAT_INZC_1",
        "ASSY, OZONATOR WITH CHAMBER B, PRODUCER SE": "SGP_TEMPLATE_AMAT_INZC_1",
        "ASSY, OZONATOR WITH CHAMBER C, PRODUCER SE": "SGP_TEMPLATE_AMAT_INZC_1",
        "ASSY, OZONATOR WITH CHAMBER A & C, PRODUCER SE": "SGP_TEMPLATE_AMAT_INZC_2",
        "ASSY, OZONATOR WITH CHAMBER B & C, PRODUCER SE": "SGP_TEMPLATE_AMAT_INZC_2",
        "ASSY, OZONATOR WITH CHAMBER A & B, PRODUCER SE": "SGP_TEMPLATE_AMAT_INZC_2",
        "ASSY, OZONATOR WITH CHAMBER A & B & C, PRODUCER SE": "SGP_TEMPLATE_AMAT_INZC_3",
    }
)


class TemplateMatchError(ValueError):
    """Raised when a classifier decision is not approved for template use."""


class TemplateVerificationRequired(TemplateMatchError):
    """Raised when a coverage-limited proposal has not been user-verified."""


def resolve_wd_template(
    decision: ClassificationDecision,
    *,
    user_verified: bool = False,
) -> str:
    if decision.status == DecisionStatus.VERIFICATION_REQUIRED and not user_verified:
        raise TemplateVerificationRequired(
            "User verification is required before selecting a WD template for "
            f"{decision.predicted_system_type or 'this classification'}"
        )
    if decision.status not in {
        DecisionStatus.CLASSIFIED,
        DecisionStatus.VERIFICATION_REQUIRED,
    }:
        raise TemplateMatchError(
            f"Decision status {decision.status.value} is not approved for template matching"
        )

    try:
        return SYSTEM_TYPE_TO_WD_TEMPLATE[decision.predicted_system_type]
    except KeyError as exc:
        raise TemplateMatchError(
            f"No WD template is mapped for {decision.predicted_system_type!r}"
        ) from exc
