"""Confluence integration client — create pages from FS analysis (L10).

Usage:
    client = ConfluenceClient()
    result = await client.create_fs_page(fs_title, sections, quality, tasks, ambiguities)
"""

import logging
from typing import Any, Dict, List

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


def _looks_unconfigured(value: str) -> bool:
    v = (value or "").strip().lower()
    if not v:
        return True
    placeholder_markers = [
        "your_",
        "example.com",
        "your-org.atlassian.net",
        "confluence.example.com",
        "you@example.com",
    ]
    return any(m in v for m in placeholder_markers)


class ConfluenceError(Exception):
    """Raised when a Confluence API call fails."""

    pass


class ConfluenceClient:
    """Confluence REST API client for creating FS documentation pages."""

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.CONFLUENCE_URL.rstrip("/")
        self.email = settings.CONFLUENCE_EMAIL
        self.api_token = settings.CONFLUENCE_API_TOKEN
        self.space_key = settings.CONFLUENCE_SPACE_KEY
        self._configured = not (
            _looks_unconfigured(self.base_url) or _looks_unconfigured(self.email) or _looks_unconfigured(self.api_token)
        )

    @property
    def is_configured(self) -> bool:
        return self._configured

    def _auth(self) -> tuple:
        return (self.email, self.api_token)

    def _build_page_content(
        self,
        sections: List[Dict[str, Any]],
        quality_score: Dict[str, Any] | None = None,
        ambiguities: List[Dict[str, Any]] | None = None,
        tasks: List[Dict[str, Any]] | None = None,
        traceability: List[Dict[str, Any]] | None = None,
    ) -> str:
        """Build Confluence Storage Format (XHTML) for the FS page."""
        parts = []

        # Quality Score Section
        if quality_score:
            overall = quality_score.get("overall", 0)
            parts.append(f"<h2>Quality Score: {overall:.0%}</h2>")
            parts.append("<table><tbody>")
            for key in ["completeness", "clarity", "consistency"]:
                val = quality_score.get(key, 0)
                parts.append(f"<tr><td><strong>{key.title()}</strong></td><td>{val:.0%}</td></tr>")
            parts.append("</tbody></table>")

        # FS Sections
        if sections:
            parts.append("<h2>Functional Specification Sections</h2>")
            for s in sections:
                heading = s.get("heading", s.get("section_heading", ""))
                content = s.get("content", s.get("text", ""))
                idx = s.get("section_index", 0)
                parts.append(f"<h3>{idx + 1}. {heading}</h3>")
                parts.append(f"<p>{content}</p>")

        # Ambiguity Summary
        if ambiguities:
            parts.append(f"<h2>Ambiguity Flags ({len(ambiguities)})</h2>")
            parts.append("<table><thead><tr><th>Section</th><th>Severity</th><th>Issue</th></tr></thead><tbody>")
            for a in ambiguities:
                parts.append(
                    f"<tr><td>{a.get('section_heading', '')}</td>"
                    f"<td>{a.get('severity', '')}</td>"
                    f"<td>{a.get('reason', '')}</td></tr>"
                )
            parts.append("</tbody></table>")

        # Task Breakdown
        if tasks:
            parts.append(f"<h2>Task Breakdown ({len(tasks)})</h2>")
            parts.append(
                "<table><thead><tr><th>ID</th><th>Title</th><th>Effort</th><th>Section</th></tr></thead><tbody>"
            )
            for t in tasks:
                parts.append(
                    f"<tr><td>{t.get('task_id', '')}</td>"
                    f"<td>{t.get('title', '')}</td>"
                    f"<td>{t.get('effort', '')}</td>"
                    f"<td>{t.get('section_heading', '')}</td></tr>"
                )
            parts.append("</tbody></table>")

        # Traceability Matrix
        if traceability:
            parts.append("<h2>Traceability Matrix</h2>")
            parts.append("<table><thead><tr><th>Task ID</th><th>Task Title</th><th>Section</th></tr></thead><tbody>")
            for t in traceability:
                parts.append(
                    f"<tr><td>{t.get('task_id', '')}</td>"
                    f"<td>{t.get('task_title', '')}</td>"
                    f"<td>{t.get('section_heading', '')}</td></tr>"
                )
            parts.append("</tbody></table>")

        return "\n".join(parts) if parts else "<p>No content generated.</p>"

    async def create_page(
        self,
        title: str,
        content: str,
        space_key: str | None = None,
    ) -> Dict[str, Any]:
        """Create a Confluence page.

        Args:
            title: Page title.
            content: Confluence Storage Format (XHTML) body.
            space_key: Target space key (defaults to configured).

        Returns:
            Dict with: id, url, title
        """
        space = space_key or self.space_key

        if not self._configured:
            logger.warning("Confluence not configured — returning simulated page")
            return {
                "id": "SIMULATED-PAGE-001",
                "url": f"https://confluence.example.com/display/{space}/{title.replace(' ', '+')}",
                "title": title,
                "simulated": True,
            }

        payload = {
            "type": "page",
            "title": title,
            "space": {"key": space},
            "body": {
                "storage": {
                    "value": content,
                    "representation": "storage",
                }
            },
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.base_url}/rest/api/content",
                    json=payload,
                    auth=self._auth(),
                    headers={"Content-Type": "application/json"},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                page_id = data.get("id", "")
                return {
                    "id": page_id,
                    "url": f"{self.base_url}/pages/viewpage.action?pageId={page_id}",
                    "title": data.get("title", title),
                    "simulated": False,
                }
        except Exception as exc:
            logger.error("Confluence page creation failed: %s", exc)
            raise ConfluenceError(f"Failed to create Confluence page: {exc}") from exc

    async def create_fs_page(
        self,
        title: str,
        sections: List[Dict[str, Any]],
        quality_score: Dict[str, Any] | None = None,
        ambiguities: List[Dict[str, Any]] | None = None,
        tasks: List[Dict[str, Any]] | None = None,
        traceability: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        """Export a full FS analysis as a Confluence page.

        Builds a rich XHTML page with all analysis results.
        """
        content = self._build_page_content(
            sections=sections,
            quality_score=quality_score,
            ambiguities=ambiguities,
            tasks=tasks,
            traceability=traceability,
        )
        return await self.create_page(title=f"FS Analysis: {title}", content=content)
