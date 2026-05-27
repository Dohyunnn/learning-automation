"""Confluence REST API v2 학습 이력 수집기.

CONFLUENCE_* 환경변수가 없으면 빈 이력을 반환한다.
"""
import base64
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ConfluenceCollector:
    """Confluence Cloud REST API v2 를 통해 기존 학습 페이지 이력을 수집한다."""

    def __init__(
        self,
        base_url: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
        space_id: str | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("CONFLUENCE_BASE_URL", "")).rstrip("/")
        self.email = email or os.getenv("CONFLUENCE_EMAIL", "")
        self.api_token = api_token or os.getenv("CONFLUENCE_API_TOKEN", "")
        self.space_id = space_id or os.getenv("CONFLUENCE_SPACE_ID", "")
        self._configured = all(
            [self.base_url, self.email, self.api_token, self.space_id]
        )
        if not self._configured:
            logger.warning("Confluence 환경변수 미설정 → 빈 이력 반환")

    @property
    def _auth_header(self) -> str:
        token = base64.b64encode(
            f"{self.email}:{self.api_token}".encode()
        ).decode()
        return f"Basic {token}"

    async def collect(self, limit: int = 50) -> list[dict[str, Any]]:
        """Confluence 스페이스의 최근 페이지 이력을 수집한다.

        Returns:
            list of { id, title, created_at, body_excerpt }
        """
        if not self._configured:
            return []

        headers = {
            "Authorization": self._auth_header,
            "Accept": "application/json",
        }
        url = f"{self.base_url}/api/v2/pages"
        params = {
            "spaceId": self.space_id,
            "limit": limit,
            "sort": "-created-date",
            "body-format": "atlas_doc_format",
        }

        async with httpx.AsyncClient(headers=headers, timeout=30) as client:
            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                pages = []
                for page in data.get("results", []):
                    pages.append(
                        {
                            "id": page.get("id"),
                            "title": page.get("title", ""),
                            "created_at": page.get("createdAt", ""),
                            "body_excerpt": str(page.get("body", ""))[:300],
                        }
                    )
                return pages
            except httpx.HTTPError as e:
                logger.error("Confluence 수집 오류: %s", e)
                return []
