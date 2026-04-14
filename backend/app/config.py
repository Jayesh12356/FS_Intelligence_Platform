"""Application settings — loaded once as singleton via get_settings()."""

from functools import lru_cache
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://fsp_user:fsp_secret@localhost:5432/fsplatform"
    DATABASE_URL_SYNC: str = "postgresql://fsp_user:fsp_secret@localhost:5432/fsplatform"

    # ── Qdrant ──────────────────────────────────────────
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""

    # ── LLM ─────────────────────────────────────────────
    LLM_PROVIDER: str = "anthropic"  # anthropic | openai | groq | openrouter
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""

    # ── Models ──────────────────────────────────────────
    EMBEDDING_PROVIDER: str = "openai"  # openai | groq | openrouter
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    PRIMARY_MODEL: str = "claude-sonnet-4-20250514"
    REASONING_MODEL: str = ""
    BUILD_MODEL: str = ""
    LONGCONTEXT_MODEL: str = ""
    FALLBACK_MODEL: str = ""

    # ── App ─────────────────────────────────────────────
    ENVIRONMENT: str = "local"
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 20
    CORS_ALLOW_ORIGINS: str = "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000,http://127.0.0.1:3001,http://frontend:3000"
    # Hybrid large-archive mode for reverse FS
    REVERSE_LARGE_UPLOAD_ENABLED: bool = True
    REVERSE_MAX_ARCHIVE_SIZE_MB: int = 300
    REVERSE_MAX_UNCOMPRESSED_MB: int = 900
    REVERSE_MAX_ARCHIVE_FILES: int = 25000
    # Parser filtering knobs
    REVERSE_INCLUDE_EXTENSIONS: str = ".py,.js,.ts,.jsx,.tsx,.java,.go"
    REVERSE_SKIP_DIRS_EXTRA: str = ""
    REVERSE_SKIP_FILES_EXTRA: str = ""
    REVERSE_MAX_FILE_SIZE_BYTES: int = 500000
    REVERSE_MAX_FILES_TO_PARSE: int = 2500
    # LLM/token knobs for reverse generation
    REVERSE_TOP_FILES_INITIAL: int = 60
    REVERSE_TOP_FILES_MAX: int = 220
    REVERSE_MAX_ENTITIES_PER_FILE: int = 40
    REVERSE_MAX_CODE_EXCERPT_CHARS: int = 12000
    REVERSE_MIN_ACCEPTABLE_FLOWS: int = 4

    # ── Optional future integrations ───────────────────
    REDIS_URL: str = ""

    # ── L10: Integrations ──────────────────────────────
    JIRA_URL: str = ""
    JIRA_EMAIL: str = ""
    JIRA_API_TOKEN: str = ""
    JIRA_PROJECT_KEY: str = "FSP"

    CONFLUENCE_URL: str = ""
    CONFLUENCE_EMAIL: str = ""
    CONFLUENCE_API_TOKEN: str = ""
    CONFLUENCE_SPACE_KEY: str = "FSP"

    # ── MCP monitoring + safety guards ─────────────────
    MCP_MONITORING_ENABLED: bool = True
    MCP_REQUIRE_ZERO_HIGH_AMBIGUITIES: bool = True
    MCP_MIN_QUALITY_SCORE: float = 90.0
    MCP_REQUIRE_TRACEABILITY: bool = True
    MCP_DRY_RUN_DEFAULT: bool = False

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def reverse_max_archive_bytes(self) -> int:
        return self.REVERSE_MAX_ARCHIVE_SIZE_MB * 1024 * 1024

    @property
    def reverse_max_uncompressed_bytes(self) -> int:
        return self.REVERSE_MAX_UNCOMPRESSED_MB * 1024 * 1024

    @property
    def reverse_include_extensions(self) -> List[str]:
        return [ext.strip().lower() for ext in self.REVERSE_INCLUDE_EXTENSIONS.split(",") if ext.strip()]

    @property
    def reverse_skip_dirs_extra(self) -> List[str]:
        return [d.strip() for d in self.REVERSE_SKIP_DIRS_EXTRA.split(",") if d.strip()]

    @property
    def reverse_skip_files_extra(self) -> List[str]:
        return [f.strip() for f in self.REVERSE_SKIP_FILES_EXTRA.split(",") if f.strip()]

    @property
    def cors_allow_origins(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ALLOW_ORIGINS.split(",") if origin.strip()]

    @property
    def upload_path(self) -> Path:
        # Render free tier uses ephemeral disk; keep writes under /tmp by default in production-like envs.
        upload_dir = self.UPLOAD_DIR
        if self.ENVIRONMENT.lower() in {"production", "render"} and upload_dir == "uploads":
            upload_dir = "/tmp/uploads"
        p = Path(upload_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings singleton."""
    return Settings()
