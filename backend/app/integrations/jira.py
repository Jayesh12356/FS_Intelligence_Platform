"""JIRA integration client — create epics and stories from FS tasks (L10).

Usage:
    client = JiraClient()
    epic_id = await client.create_epic("Payment FS", "Payment module specification")
    story_id = await client.create_story(task_dict, epic_id)
"""

import logging
from typing import Any, Dict, List, Optional

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
        "jira.example.com",
        "you@example.com",
    ]
    return any(m in v for m in placeholder_markers)


class JiraError(Exception):
    """Raised when a JIRA API call fails."""
    pass


class JiraClient:
    """JIRA REST API v3 client for creating epics and stories."""

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.JIRA_URL.rstrip("/")
        self.email = settings.JIRA_EMAIL
        self.api_token = settings.JIRA_API_TOKEN
        self.project_key = settings.JIRA_PROJECT_KEY
        self._configured = not (
            _looks_unconfigured(self.base_url)
            or _looks_unconfigured(self.email)
            or _looks_unconfigured(self.api_token)
        )

    @property
    def is_configured(self) -> bool:
        return self._configured

    def _headers(self) -> dict:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _auth(self) -> tuple:
        return (self.email, self.api_token)

    async def create_epic(
        self,
        title: str,
        description: str = "",
    ) -> Dict[str, Any]:
        """Create a JIRA epic for an FS document.

        Args:
            title: Epic title (FS document name).
            description: Epic description.

        Returns:
            Dict with: id, key, url
        """
        if not self._configured:
            # Simulate for demo/test
            logger.warning("JIRA not configured — returning simulated epic")
            return {
                "id": "SIMULATED-EPIC-001",
                "key": f"{self.project_key}-001",
                "url": f"https://jira.example.com/browse/{self.project_key}-001",
                "simulated": True,
            }

        payload = {
            "fields": {
                "project": {"key": self.project_key},
                "summary": title,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": description or title}],
                        }
                    ],
                },
                "issuetype": {"name": "Epic"},
            }
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.base_url}/rest/api/3/issue",
                    json=payload,
                    headers=self._headers(),
                    auth=self._auth(),
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                return {
                    "id": data.get("id", ""),
                    "key": data.get("key", ""),
                    "url": f"{self.base_url}/browse/{data.get('key', '')}",
                    "simulated": False,
                }
        except Exception as exc:
            logger.error("JIRA epic creation failed: %s", exc)
            raise JiraError(f"Failed to create JIRA epic: {exc}") from exc

    async def create_story(
        self,
        task: Dict[str, Any],
        epic_key: str = "",
    ) -> Dict[str, Any]:
        """Create a JIRA story from an FS task.

        Args:
            task: Dict with task_id, title, description, acceptance_criteria, effort, tags.
            epic_key: Parent epic key for linking.

        Returns:
            Dict with: id, key, url
        """
        title = task.get("title", "Untitled Task")
        description = task.get("description", "")
        criteria = task.get("acceptance_criteria", [])
        effort = task.get("effort", "MEDIUM")
        tags = task.get("tags", [])

        # Build description with acceptance criteria
        desc_parts = [description]
        if criteria:
            desc_parts.append("\n\n*Acceptance Criteria:*")
            for i, ac in enumerate(criteria, 1):
                desc_parts.append(f"  {i}. {ac}")
        desc_parts.append(f"\n*Effort:* {effort}")
        if tags:
            desc_parts.append(f"*Tags:* {', '.join(tags)}")
        full_desc = "\n".join(desc_parts)

        if not self._configured:
            task_id = task.get("task_id", "T-001")
            logger.warning("JIRA not configured — returning simulated story for %s", task_id)
            return {
                "id": f"SIMULATED-{task_id}",
                "key": f"{self.project_key}-{task_id}",
                "url": f"https://jira.example.com/browse/{self.project_key}-{task_id}",
                "simulated": True,
            }

        payload = {
            "fields": {
                "project": {"key": self.project_key},
                "summary": title,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": full_desc}],
                        }
                    ],
                },
                "issuetype": {"name": "Story"},
            }
        }

        # Link to epic if provided
        if epic_key:
            payload["fields"]["parent"] = {"key": epic_key}

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.base_url}/rest/api/3/issue",
                    json=payload,
                    headers=self._headers(),
                    auth=self._auth(),
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                return {
                    "id": data.get("id", ""),
                    "key": data.get("key", ""),
                    "url": f"{self.base_url}/browse/{data.get('key', '')}",
                    "simulated": False,
                }
        except Exception as exc:
            logger.error("JIRA story creation failed: %s", exc)
            raise JiraError(f"Failed to create JIRA story: {exc}") from exc

    async def export_fs_tasks(
        self,
        fs_title: str,
        tasks: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Export all FS tasks as a JIRA epic + stories.

        Args:
            fs_title: FS document title for the epic.
            tasks: List of task dicts from the pipeline.

        Returns:
            Dict with: epic (dict), stories (list of dicts), total
        """
        epic = await self.create_epic(fs_title, f"Auto-generated from FS: {fs_title}")
        epic_key = epic.get("key", "")

        stories = []
        for task in tasks:
            story = await self.create_story(task, epic_key)
            stories.append(story)

        logger.info(
            "JIRA export complete: epic=%s, stories=%d",
            epic_key, len(stories),
        )

        return {
            "epic": epic,
            "stories": stories,
            "total": len(stories),
        }
