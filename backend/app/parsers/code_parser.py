"""Code parser — extracts structured data from uploaded codebases (L8).

Parses zip archives of source code, extracting:
- File list (filtered by language)
- Functions, classes, methods with signatures and docstrings
- Language detection and LOC counts

Supports: .py, .js, .ts, .java, .go
Skips: node_modules, __pycache__, .git, build, dist, venv, .env, etc.
"""

import ast
import fnmatch
import logging
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from app.config import get_settings
from app.pipeline.state import CodebaseSnapshot, CodeEntity, CodeFile

logger = logging.getLogger(__name__)

# ── Configuration ───────────────────────────────────────

SUPPORTED_EXTENSIONS: Set[str] = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go"}

SKIP_DIRS: Set[str] = {
    "node_modules", "__pycache__", ".git", ".svn", ".hg",
    "build", "dist", "venv", ".venv", "env", ".env",
    ".idea", ".vscode", ".mypy_cache", ".pytest_cache",
    "vendor", "target", "bin", "obj", ".next", "out",
    "coverage", ".tox", "eggs", ".eggs",
}

SKIP_FILES: Set[str] = {
    ".gitignore", ".dockerignore", "package-lock.json",
    "yarn.lock", "pnpm-lock.yaml", "Pipfile.lock",
    "poetry.lock",
}

LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
}

MAX_FILE_SIZE_BYTES = 500_000  # Skip files > 500KB


def _build_filter_config() -> dict:
    """Build parser filtering config from settings."""
    settings = get_settings()
    include_ext = set(settings.reverse_include_extensions) or set(SUPPORTED_EXTENSIONS)
    # Normalize extensions to `.ext` format
    normalized_ext = set()
    for ext in include_ext:
        e = ext.strip().lower()
        if not e:
            continue
        if not e.startswith("."):
            e = f".{e}"
        normalized_ext.add(e)

    return {
        "skip_dirs": set(SKIP_DIRS).union(set(settings.reverse_skip_dirs_extra)),
        "skip_files": set(SKIP_FILES).union(set(settings.reverse_skip_files_extra)),
        "include_extensions": normalized_ext,
        "max_file_size_bytes": max(int(settings.REVERSE_MAX_FILE_SIZE_BYTES), 1024),
        "max_files_to_parse": max(int(settings.REVERSE_MAX_FILES_TO_PARSE), 50),
    }


def _preflight_zip(zip_path: str) -> Tuple[int, int]:
    """Validate archive characteristics to avoid zip-bomb style payloads."""
    settings = get_settings()
    with zipfile.ZipFile(zip_path, "r") as zf:
        infos = zf.infolist()
        if len(infos) > settings.REVERSE_MAX_ARCHIVE_FILES:
            raise ValueError(
                f"Archive has too many files ({len(infos)} > {settings.REVERSE_MAX_ARCHIVE_FILES})"
            )

        total_uncompressed = 0
        total_compressed = 0
        for info in infos:
            total_uncompressed += int(info.file_size or 0)
            total_compressed += int(info.compress_size or 0)

        if total_uncompressed > settings.reverse_max_uncompressed_bytes:
            raise ValueError(
                "Archive expands beyond safe limit "
                f"({total_uncompressed} bytes > {settings.reverse_max_uncompressed_bytes} bytes)"
            )

        # Compression ratio guard (very high expansion tends to be suspicious)
        if total_compressed > 0:
            ratio = total_uncompressed / max(total_compressed, 1)
            if ratio > 200:
                raise ValueError(f"Archive compression ratio too high ({ratio:.1f}x)")

        return len(infos), total_uncompressed


# ── Python AST Extraction ───────────────────────────────


def _extract_python_entities(content: str) -> List[CodeEntity]:
    """Extract functions, classes, and methods from Python source using AST."""
    entities: List[CodeEntity] = []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return entities

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            docstring = ast.get_docstring(node)
            # Build signature
            args = []
            for arg in node.args.args:
                arg_str = arg.arg
                if arg.annotation:
                    try:
                        arg_str += f": {ast.unparse(arg.annotation)}"
                    except Exception:
                        pass
                args.append(arg_str)

            returns = ""
            if node.returns:
                try:
                    returns = f" -> {ast.unparse(node.returns)}"
                except Exception:
                    pass

            sig = f"def {node.name}({', '.join(args)}){returns}"

            entities.append(CodeEntity(
                name=node.name,
                entity_type="function",
                docstring=docstring,
                signature=sig,
                line_number=node.lineno,
            ))

        elif isinstance(node, ast.ClassDef):
            docstring = ast.get_docstring(node)
            bases = []
            for base in node.bases:
                try:
                    bases.append(ast.unparse(base))
                except Exception:
                    bases.append("?")

            sig = f"class {node.name}"
            if bases:
                sig += f"({', '.join(bases)})"

            entities.append(CodeEntity(
                name=node.name,
                entity_type="class",
                docstring=docstring,
                signature=sig,
                line_number=node.lineno,
            ))

            # Extract methods from the class
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_doc = ast.get_docstring(item)
                    method_args = []
                    for arg in item.args.args:
                        arg_str = arg.arg
                        if arg.annotation:
                            try:
                                arg_str += f": {ast.unparse(arg.annotation)}"
                            except Exception:
                                pass
                        method_args.append(arg_str)

                    method_returns = ""
                    if item.returns:
                        try:
                            method_returns = f" -> {ast.unparse(item.returns)}"
                        except Exception:
                            pass

                    method_sig = f"{node.name}.{item.name}({', '.join(method_args)}){method_returns}"

                    entities.append(CodeEntity(
                        name=f"{node.name}.{item.name}",
                        entity_type="method",
                        docstring=method_doc,
                        signature=method_sig,
                        line_number=item.lineno,
                    ))

    return entities


# ── Regex-Based Extraction (JS/TS/Java/Go) ──────────────


# Patterns for function/class extraction by language
JS_FUNCTION_RE = re.compile(
    r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)",
    re.MULTILINE,
)
JS_CLASS_RE = re.compile(
    r"(?:export\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?\s*\{",
    re.MULTILINE,
)
JS_ARROW_RE = re.compile(
    r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>",
    re.MULTILINE,
)

JAVA_METHOD_RE = re.compile(
    r"(?:public|private|protected|static)\s+\w+\s+(\w+)\s*\(([^)]*)\)",
    re.MULTILINE,
)
JAVA_CLASS_RE = re.compile(
    r"(?:public|private)?\s*(?:abstract\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?",
    re.MULTILINE,
)

GO_FUNC_RE = re.compile(
    r"func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(([^)]*)\)",
    re.MULTILINE,
)


def _extract_jsdoc_comments(content: str) -> dict[int, str]:
    """Extract JSDoc-style comments and map them to the line after the comment."""
    comments: dict[int, str] = {}
    jsdoc_re = re.compile(r"/\*\*(.*?)\*/", re.DOTALL)
    for match in jsdoc_re.finditer(content):
        # Find the line number after the comment
        end_pos = match.end()
        line_num = content[:end_pos].count("\n") + 1
        doc = match.group(1).strip()
        # Clean up * prefixes
        doc = re.sub(r"^\s*\*\s?", "", doc, flags=re.MULTILINE).strip()
        comments[line_num] = doc
    return comments


def _extract_generic_entities(content: str, language: str) -> List[CodeEntity]:
    """Extract entities from JS/TS/Java/Go source using regex."""
    entities: List[CodeEntity] = []
    lines = content.split("\n")
    jsdoc = _extract_jsdoc_comments(content) if language in ("javascript", "typescript") else {}

    if language in ("javascript", "typescript"):
        for match in JS_FUNCTION_RE.finditer(content):
            line_num = content[:match.start()].count("\n") + 1
            doc = jsdoc.get(line_num, None)
            entities.append(CodeEntity(
                name=match.group(1),
                entity_type="function",
                docstring=doc,
                signature=f"function {match.group(1)}({match.group(2)})",
                line_number=line_num,
            ))

        for match in JS_ARROW_RE.finditer(content):
            line_num = content[:match.start()].count("\n") + 1
            doc = jsdoc.get(line_num, None)
            entities.append(CodeEntity(
                name=match.group(1),
                entity_type="function",
                docstring=doc,
                signature=f"const {match.group(1)} = (...) =>",
                line_number=line_num,
            ))

        for match in JS_CLASS_RE.finditer(content):
            line_num = content[:match.start()].count("\n") + 1
            doc = jsdoc.get(line_num, None)
            sig = f"class {match.group(1)}"
            if match.group(2):
                sig += f" extends {match.group(2)}"
            entities.append(CodeEntity(
                name=match.group(1),
                entity_type="class",
                docstring=doc,
                signature=sig,
                line_number=line_num,
            ))

    elif language == "java":
        for match in JAVA_CLASS_RE.finditer(content):
            line_num = content[:match.start()].count("\n") + 1
            sig = f"class {match.group(1)}"
            if match.group(2):
                sig += f" extends {match.group(2)}"
            entities.append(CodeEntity(
                name=match.group(1),
                entity_type="class",
                signature=sig,
                line_number=line_num,
            ))

        for match in JAVA_METHOD_RE.finditer(content):
            line_num = content[:match.start()].count("\n") + 1
            entities.append(CodeEntity(
                name=match.group(1),
                entity_type="method",
                signature=f"{match.group(1)}({match.group(2)})",
                line_number=line_num,
            ))

    elif language == "go":
        for match in GO_FUNC_RE.finditer(content):
            line_num = content[:match.start()].count("\n") + 1
            # Check for comment on line above
            doc = None
            if line_num > 1:
                prev_line = lines[line_num - 2].strip()
                if prev_line.startswith("//"):
                    doc = prev_line.lstrip("/ ").strip()

            entities.append(CodeEntity(
                name=match.group(1),
                entity_type="function",
                docstring=doc,
                signature=f"func {match.group(1)}({match.group(2)})",
                line_number=line_num,
            ))

    return entities


# ── File Parsing ────────────────────────────────────────


def _should_skip_file(path: Path, filter_cfg: Optional[dict] = None) -> bool:
    """Check if a file should be skipped."""
    cfg = filter_cfg or {
        "skip_dirs": SKIP_DIRS,
        "skip_files": SKIP_FILES,
        "include_extensions": SUPPORTED_EXTENSIONS,
    }
    skip_dirs = cfg.get("skip_dirs", SKIP_DIRS)
    skip_files = cfg.get("skip_files", SKIP_FILES)
    include_extensions = cfg.get("include_extensions", SUPPORTED_EXTENSIONS)

    # Check if any parent directory is in skip list
    for part in path.parts:
        if part in skip_dirs:
            return True

    # Check filename
    if path.name in skip_files:
        return True

    # Check extension
    if path.suffix.lower() not in include_extensions:
        return True

    # Skip minified assets when uploaded inside source trees
    if path.name.endswith(".min.js") or path.name.endswith(".bundle.js"):
        return True

    # Skip obvious generated files
    generated_globs = ("*.generated.*", "*.gen.*", "*.pb.*", "*.snap")
    for pattern in generated_globs:
        if fnmatch.fnmatch(path.name, pattern):
            return True

    return False


def _parse_single_file(file_path: Path, base_dir: Path, filter_cfg: Optional[dict] = None) -> Optional[CodeFile]:
    """Parse a single source code file."""
    relative_path = str(file_path.relative_to(base_dir)).replace("\\", "/")
    cfg = filter_cfg or {}
    max_file_size = int(cfg.get("max_file_size_bytes", MAX_FILE_SIZE_BYTES))

    # Check file size
    try:
        file_size = file_path.stat().st_size
        if file_size > max_file_size:
            logger.debug("Skipping large file: %s (%d bytes)", relative_path, file_size)
            return None
    except OSError:
        return None

    # Determine language
    ext = file_path.suffix.lower()
    language = LANGUAGE_MAP.get(ext, "")

    # Read content
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.warning("Failed to read %s: %s", relative_path, exc)
        return None

    # Skip huge boilerplate text files with no actionable symbols
    if len(content) > 250_000 and content.count("\n") > 3000:
        return None

    # Extract entities
    if language == "python":
        entities = _extract_python_entities(content)
    else:
        entities = _extract_generic_entities(content, language)

    line_count = content.count("\n") + 1
    has_docstrings = any(e.docstring for e in entities)

    return CodeFile(
        path=relative_path,
        language=language,
        content=content,
        entities=entities,
        line_count=line_count,
        has_docstrings=has_docstrings,
    )


def _score_code_file(code_file: CodeFile) -> int:
    """Assign a heuristic signal score for reverse-FS relevance."""
    path_l = code_file.path.lower()
    score = 0

    # Structural signals
    score += min(len(code_file.entities), 60) * 3
    if code_file.has_docstrings:
        score += 10

    # Prioritize feature/entrypoint files
    high_signal_parts = [
        "route", "router", "controller", "service", "handler", "api",
        "auth", "payment", "order", "user", "main", "app", "module",
        "feature", "workflow",
    ]
    for token in high_signal_parts:
        if token in path_l:
            score += 8

    # De-prioritize obvious infra/test files
    low_signal_parts = ["test", "spec", "mock", "fixture", "config", "migration", "seed"]
    for token in low_signal_parts:
        if token in path_l:
            score -= 6

    # Slight bump for longer business logic files
    score += min(code_file.line_count // 80, 20)
    return score


# ── Main Parse Function ────────────────────────────────


def parse_codebase(zip_path: str) -> CodebaseSnapshot:
    """Parse a codebase from a zip archive.

    Extracts the zip, walks all source files, extracts code entities,
    and returns a CodebaseSnapshot.

    Args:
        zip_path: Path to the uploaded zip file.

    Returns:
        CodebaseSnapshot with all extracted files and entities.

    Raises:
        ValueError: If the zip file is invalid or empty.
    """
    zip_path_obj = Path(zip_path)
    if not zip_path_obj.exists():
        raise ValueError(f"Zip file not found: {zip_path}")

    if not zipfile.is_zipfile(zip_path):
        raise ValueError(f"Not a valid zip file: {zip_path}")

    archive_file_count, archive_uncompressed_bytes = _preflight_zip(zip_path)
    filter_cfg = _build_filter_config()

    # Extract to temp directory
    extract_dir = tempfile.mkdtemp(prefix="codeparse_")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

        extract_path = Path(extract_dir)

        # Find the actual root (skip single-folder wrapper)
        children = list(extract_path.iterdir())
        if len(children) == 1 and children[0].is_dir():
            root_dir = children[0]
        else:
            root_dir = extract_path

        # Walk and parse files
        files: List[CodeFile] = []
        languages: dict[str, int] = {}
        parser_stats: Dict[str, int] = {
            "archive_files_total": archive_file_count,
            "archive_uncompressed_bytes": archive_uncompressed_bytes,
            "walked_files": 0,
            "parsed_files": 0,
            "skipped_files": 0,
            "skipped_by_filter": 0,
            "skipped_by_size": 0,
            "skipped_by_limit": 0,
        }
        scored: List[Tuple[int, CodeFile]] = []

        for file_path in sorted(root_dir.rglob("*")):
            if not file_path.is_file():
                continue
            parser_stats["walked_files"] += 1
            relative = file_path.relative_to(root_dir)
            if _should_skip_file(relative, filter_cfg):
                parser_stats["skipped_files"] += 1
                parser_stats["skipped_by_filter"] += 1
                continue

            if len(scored) >= int(filter_cfg["max_files_to_parse"]):
                parser_stats["skipped_files"] += 1
                parser_stats["skipped_by_limit"] += 1
                continue

            code_file = _parse_single_file(file_path, root_dir, filter_cfg)
            if code_file:
                score = _score_code_file(code_file)
                scored.append((score, code_file))
                lang = code_file.language
                languages[lang] = languages.get(lang, 0) + 1
                parser_stats["parsed_files"] += 1
            else:
                parser_stats["skipped_files"] += 1
                parser_stats["skipped_by_size"] += 1

        if not scored:
            raise ValueError("No supported source files found in the archive")

        # Keep highest signal files first for downstream reverse generation.
        scored.sort(key=lambda x: x[0], reverse=True)
        files = [f for _, f in scored]

        total_lines = sum(f.line_count for f in files)
        primary_language = max(languages, key=languages.get) if languages else ""

        logger.info(
            "Parsed codebase: %d files, %d lines, primary language: %s, languages: %s, stats=%s",
            len(files), total_lines, primary_language, languages, parser_stats,
        )

        return CodebaseSnapshot(
            files=files,
            primary_language=primary_language,
            total_files=len(files),
            total_lines=total_lines,
            languages=languages,
            parser_stats=parser_stats,
        )

    finally:
        # Clean up extracted files
        shutil.rmtree(extract_dir, ignore_errors=True)
