from __future__ import annotations

from jobos.schemas import FieldRisk

RED_KEYWORDS = [
    "right to work",
    "sponsorship",
    "visa",
    "criminal",
    "conviction",
    "background check",
    "certify",
    "accurate",
    "ethnicity",
    "religion",
    "disability",
    "gender",
    "sexual orientation",
    "veteran",
]

AMBER_KEYWORDS = [
    "salary",
    "notice",
    "why",
    "motivation",
    "cover letter",
    "additional information",
]

GREEN_KEYWORDS = [
    "name",
    "email",
    "phone",
    "linkedin",
    "education",
    "employer",
    "university",
]


def classify_field(field_label: str, field_type: str = "unknown", suggested_value: str | None = None) -> FieldRisk:
    label = field_label.lower()
    if any(k in label for k in RED_KEYWORDS):
        return FieldRisk(
            field_label=field_label,
            field_type=field_type,
            risk_level="red",
            suggested_value=None,
            requires_manual_approval=True,
            reason="Sensitive, legal, demographic or certification field. Must be completed manually.",
        )
    if any(k in label for k in AMBER_KEYWORDS):
        return FieldRisk(
            field_label=field_label,
            field_type=field_type,
            risk_level="amber",
            suggested_value=suggested_value,
            requires_manual_approval=True,
            reason="Judgement-based field. Agent may draft, but user should review.",
        )
    if any(k in label for k in GREEN_KEYWORDS):
        return FieldRisk(
            field_label=field_label,
            field_type=field_type,
            risk_level="green",
            suggested_value=suggested_value,
            requires_manual_approval=False,
            reason="Low-risk identity/profile field.",
        )
    return FieldRisk(
        field_label=field_label,
        field_type=field_type,
        risk_level="amber",
        suggested_value=suggested_value,
        requires_manual_approval=True,
        reason="Unknown field type. Defaulting to human review.",
    )
