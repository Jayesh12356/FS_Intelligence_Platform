"""Compliance-tag detection prompt (quality node, v2)."""

from __future__ import annotations

from app.pipeline.prompts.master_template import (
    FewShotExample,
    OutputContract,
    OutputShape,
    PromptSpec,
)

NAME = "analysis.quality.compliance"

VALID_TAGS = ("payments", "auth", "pii", "external_api", "security", "data_retention")

SPEC = PromptSpec(
    name=NAME,
    role=(
        "You are a compliance officer reviewing Functional Specifications for "
        "regulatory and security risk. You tag sections that require special "
        "implementation attention due to legal, financial, or data-protection "
        "obligations."
    ),
    mission=(
        "Identify which compliance domains the section implements. Apply tags "
        "only when the section describes concrete, actionable functionality "
        "in that domain — never for passing references."
    ),
    constraints=[
        f"Valid tags: {', '.join(VALID_TAGS)}.",
        "`payments` → charges, refunds, invoicing, billing cycles, payment-method storage.",
        "`auth` → login, MFA, SSO, tokens, role checks, permission gates, sessions.",
        "`pii` → collecting, storing, processing, or transmitting names, emails, phone numbers, addresses, IDs, health records, biometrics, location.",
        "`external_api` → third-party REST/SOAP, webhooks, OAuth with external providers, partner data exchange.",
        "`security` → encryption, hashing, key management, input sanitisation, CORS/CSP, firewall, intrusion detection.",
        "`data_retention` → how long data is kept, when it is deleted, archival, backup/restore, right-to-erasure flows, audit log retention.",
        "A section may carry MULTIPLE tags when it crosses domains (registration is both `auth` and `pii`).",
        "`reason` must cite the SPECIFIC text or functionality that triggers the tag.",
    ],
    output_contract=OutputContract(
        shape=OutputShape.JSON_ARRAY,
        schema={
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["tag", "reason"],
                "properties": {
                    "tag": {"type": "string", "enum": list(VALID_TAGS)},
                    "reason": {"type": "string", "minLength": 1},
                },
            },
        },
        empty_value="[]",
        notes="Empty array `[]` if the section has no compliance-relevant functionality.",
    ),
    few_shot=[
        FewShotExample(
            label="Registration triggers auth + pii",
            input_snippet=(
                '"Users shall register with email, full name, and phone '
                "number. The system shall issue a JWT session token with "
                'role-based access (admin vs member)."'
            ),
            expected_output=(
                '[{"tag": "pii", "reason": "Collects and stores user\'s full '
                'name, email, and phone number during registration."}, '
                '{"tag": "auth", "reason": "Issues JWT session tokens and '
                'enforces role-based access control (admin vs member)."}]'
            ),
        ),
    ],
    refusal=("If the section describes no implementable functionality in any of the six domains, return `[]`."),
    use_xml_scaffold=True,
    thinking_protocol=(
        "Tag in three silent passes.\n"
        "Pass 1 — Identify behaviours actually described "
        "(verbs + nouns). Ignore passing references in headings or "
        "summaries.\n"
        "Pass 2 — For each behaviour, evaluate the six compliance "
        "domains and decide whether the section IMPLEMENTS that "
        "domain (concrete functionality) or merely MENTIONS it.\n"
        "Pass 3 — A section may carry multiple tags only when it "
        "implements multiple distinct domains; resist tagging the "
        "same behaviour twice. Then emit JSON."
    ),
    self_check=(
        "Before returning, verify each tag:\n"
        "1. Belongs to the closed enum.\n"
        "2. `reason` cites a specific phrase or behaviour from the "
        "section text — not abstract domain knowledge.\n"
        "3. Multiple tags are only used when functionality genuinely "
        "spans domains (e.g. registration = auth + pii)."
    ),
)

USER_TEMPLATE = (
    "Determine which compliance domains this section's requirements fall "
    "under. Tag only domains where the section describes concrete, "
    "implementable functionality — not passing references.\n\n"
    'Section: "{heading}"\n\n{content}'
)


def build(heading: str, content: str) -> tuple[str, str]:
    system = SPEC.system()
    user = SPEC.user(USER_TEMPLATE.format(heading=heading, content=content))
    return system, user


__all__ = ["NAME", "SPEC", "VALID_TAGS", "build"]
