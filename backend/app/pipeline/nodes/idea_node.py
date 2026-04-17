"""Idea-to-FS generation node — converts a product idea into a professional FS document."""

import logging
from typing import Optional

from app.orchestration.pipeline_llm import pipeline_call_llm, pipeline_call_llm_json

logger = logging.getLogger(__name__)

QUICK_SYSTEM_PROMPT = """\
You are an elite enterprise software architect and business analyst. Your job is to \
transform a brief product idea into a comprehensive, industry-grade Functional \
Specification (FS) document that a development team can immediately build from.

The FS MUST include these sections, each with deep technical and business detail:
1. OVERVIEW — product vision, goals, target market, success metrics
2. USER ROLES & PERSONAS — distinct user types, their goals, permissions
3. CORE FEATURES — detailed feature descriptions with user stories and acceptance criteria
4. NON-FUNCTIONAL REQUIREMENTS — performance, scalability, availability, security, compliance
5. API CONTRACTS — key API endpoints with methods, paths, request/response schemas
6. DATA MODELS — entities, relationships, key fields with types
7. SECURITY & AUTHENTICATION — auth flow, authorization, data protection
8. ERROR HANDLING & EDGE CASES — failure modes, recovery, boundary conditions
9. INTEGRATION POINTS — third-party services, webhooks, external APIs
10. ACCEPTANCE CRITERIA — measurable definition of done per feature

Rules:
- Write at an enterprise production level, not a toy/demo level.
- Be specific: include real field names, real API paths, real error codes.
- Think about scale: assume thousands of concurrent users.
- Cover what most specs miss: rate limiting, pagination, caching, audit trails.
- Use numbered sections with clear headings.
- Output ONLY the FS document text. No meta-commentary."""

GUIDED_QUESTIONS_SYSTEM = """\
You are an expert business analyst conducting a requirements discovery session. \
Given a product idea, generate exactly 6 targeted clarifying questions that will \
help produce a comprehensive Functional Specification. Each question should probe \
a different dimension: target users, scale/performance, integrations, tech stack, \
compliance/security, and monetization/business model.

Return a JSON array of objects with keys: "id" (q1..q6), "question" (the text), \
"dimension" (which dimension it probes), "options" (array of 3-4 suggested answers, \
or empty array if open-ended)."""

GUIDED_GENERATE_SYSTEM = """\
You are an elite enterprise software architect. Using the product idea AND the \
user's answers to discovery questions, generate a comprehensive, industry-grade \
Functional Specification document. Follow the exact same structure and quality \
standards as a quick-mode generation, but tailor every section to the specific \
answers provided. The FS should be deeply customized to the user's stated \
preferences for scale, tech stack, integrations, compliance, and business model."""


async def generate_fs_quick(
    idea: str,
    industry: Optional[str] = None,
    complexity: Optional[str] = None,
) -> str:
    """Generate a full FS document from a brief idea description."""
    context_parts = [f"Product Idea: {idea}"]
    if industry:
        context_parts.append(f"Industry: {industry}")
    if complexity:
        context_parts.append(f"Complexity Level: {complexity}")

    prompt = "\n".join(context_parts)

    logger.info("Generating FS from idea (quick mode): %.100s…", idea)
    result = await pipeline_call_llm(
        prompt=prompt,
        system=QUICK_SYSTEM_PROMPT,
        max_tokens=8192,
        temperature=0.3,
        role="longcontext",
    )
    return result.strip()


async def generate_guided_questions(idea: str) -> list[dict]:
    """Generate clarifying questions for the guided flow."""
    result = await pipeline_call_llm_json(
        prompt=f"Product Idea: {idea}",
        system=GUIDED_QUESTIONS_SYSTEM,
        max_tokens=2048,
        temperature=0.4,
    )

    if isinstance(result, list):
        return result
    if isinstance(result, dict) and "questions" in result:
        return result["questions"]
    return []


async def generate_fs_guided(
    idea: str,
    answers: dict,
    industry: Optional[str] = None,
    complexity: Optional[str] = None,
) -> str:
    """Generate FS using the idea plus user's answers to guided questions."""
    parts = [f"Product Idea: {idea}"]
    if industry:
        parts.append(f"Industry: {industry}")
    if complexity:
        parts.append(f"Complexity: {complexity}")
    parts.append("\nDiscovery Answers:")
    for q_id, answer in answers.items():
        parts.append(f"  {q_id}: {answer}")

    prompt = "\n".join(parts)

    logger.info("Generating FS from idea (guided mode): %.100s…", idea)
    result = await pipeline_call_llm(
        prompt=prompt,
        system=GUIDED_GENERATE_SYSTEM,
        max_tokens=8192,
        temperature=0.3,
        role="longcontext",
    )
    return result.strip()
