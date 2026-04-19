"""Reverse-FS module summary prompt (v2)."""

from __future__ import annotations

from app.pipeline.prompts.master_template import (
    OutputContract,
    OutputShape,
    PromptSpec,
)

NAME = "reverse.module_summary"

SPEC = PromptSpec(
    name=NAME,
    role=(
        "You are a code archaeologist reverse-engineering a codebase into "
        "documentation. Given a source file, you produce a precise "
        "functional summary that captures WHAT the module does — never HOW "
        "it does it internally."
    ),
    mission=(
        "Summarise one source file into a single, strictly-shaped module record suitable for downstream FS generation."
    ),
    constraints=[
        "`purpose` is exactly ONE sentence, starts with a verb (Handles/Manages/Provides/Implements). No conjunctions.",
        "`key_components` lists 3-10 public/exported functions and classes. Omit internal helpers.",
        "`dependencies` names only external packages or services; never standard-library imports or sibling modules.",
        "`summary` is 2-3 sentences covering (1) inputs, (2) processing/transformation, (3) outputs or side-effects — readable by someone who has never seen the code.",
        "`module_name` is the filename without extension.",
    ],
    output_contract=OutputContract(
        shape=OutputShape.JSON_OBJECT,
        schema={
            "type": "object",
            "additionalProperties": False,
            "required": [
                "module_name",
                "purpose",
                "key_components",
                "dependencies",
                "summary",
            ],
            "properties": {
                "module_name": {"type": "string", "minLength": 1},
                "purpose": {"type": "string", "minLength": 1},
                "key_components": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "maxItems": 10,
                },
                "dependencies": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "summary": {"type": "string", "minLength": 1},
            },
        },
        empty_value="{}",
    ),
    few_shot=[],
    refusal=(
        "If the file is empty or unreadable, return an object with "
        "`module_name` set and `purpose: 'Unreadable file'`. Never return "
        "prose."
    ),
)

USER_TEMPLATE = (
    "Summarise this source file's functional purpose.\n\n"
    "File: {file_path}\nLanguage: {language}\nEntities (functions/classes):\n"
    "{entities}\n\nCode (first 200 lines):\n{code_excerpt}\n\n"
    "Return a JSON module summary."
)


def build(file_path: str, language: str, entities: str, code_excerpt: str) -> tuple[str, str]:
    system = SPEC.system()
    user = SPEC.user(
        USER_TEMPLATE.format(
            file_path=file_path,
            language=language,
            entities=entities,
            code_excerpt=code_excerpt,
        )
    )
    return system, user


__all__ = ["NAME", "SPEC", "build"]
