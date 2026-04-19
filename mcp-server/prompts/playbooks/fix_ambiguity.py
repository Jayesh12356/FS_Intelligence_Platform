"""Playbook: fix_single_ambiguity — deterministic one-flag resolution."""

from __future__ import annotations


def build(document_id: str, flag_id: str) -> str:
    """Render the focused single-ambiguity resolution playbook."""
    return f"""# RESOLVE AMBIGUITY — Document {document_id} / Flag {flag_id}

Goal: turn one ambiguous requirement into a concrete, implementation-
ready statement that a developer can ship without further discussion.

DO NOT:
  - Submit a vague resolution ("make it faster", "should be secure").
  - Resolve a flag without checking get_debate_results first — the
    multi-agent debate usually contains the right answer.
  - Call resolve_ambiguity without first reading flagged_text and
    reason — you need the exact text you are replacing.

STEPS:

1) get_ambiguities("{document_id}")
     Find the entry with id="{flag_id}". Read:
       - flagged_text (the ambiguous sentence)
       - reason (why it is ambiguous)
       - severity (HIGH / MEDIUM / LOW)

2) get_debate_results("{document_id}")
     If a debate exists for this flag, read the arbiter's final
     reasoning and prefer it as the basis for your resolution.

3) DRAFT the resolution. It MUST:
     - Replace the flagged text entirely (not a comment on it).
     - Cite specific numbers, conditions, thresholds, or behaviours.
     - Be a complete sentence or paragraph that implements directly.
     Examples:
       BAD : "The API should be fast."
       GOOD: "The API shall respond within 200 ms at the 95th
              percentile under 1000 concurrent users."

4) resolve_ambiguity(
     document_id="{document_id}",
     flag_id="{flag_id}",
     resolution="<your resolution text>",
   )

5) VERIFY
     get_ambiguities("{document_id}") — confirm the flag is resolved.

6) refresh_quality_score("{document_id}")
     Confirm quality held or improved. If it dropped, inspect the
     returned sub-scores; the resolution may have introduced a new
     contradiction that needs a follow-up pass.
"""
