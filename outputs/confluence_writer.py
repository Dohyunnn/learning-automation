"""Confluence REST API v2 페이지 자동 생성기.

Confluence 환경변수 미설정 시 에러를 기록하고 graceful degradation.
"""
import base64
import logging
import os
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def _to_html(
    topic: str,
    depth: str,
    curriculum: dict[str, Any],
    resources: list[dict[str, Any]],
    validation_result: dict[str, Any],
) -> str:
    """커리큘럼 데이터를 Confluence HTML body로 변환한다."""
    score = validation_result.get("score", 0)
    passed = validation_result.get("passed", False)
    stages = curriculum.get("stages", [])
    objectives = curriculum.get("objectives", [])

    objs_html = "".join(f"<li>{o}</li>" for o in objectives)
    prereqs = "".join(
        f"<li>{p}</li>" for p in curriculum.get("prerequisites", [])
    )

    stages_html = ""
    for s in stages:
        topics_li = "".join(f"<li>{t}</li>" for t in s.get("topics", []))
        stages_html += f"""
<h3>Stage {s.get('stage', '?')}: {s.get('title', '')}</h3>
<p><strong>예상 소요:</strong> {s.get('duration_hours', '?')}시간 &nbsp;
   <strong>완료 기준:</strong> {s.get('milestone', '')}</p>
<ul>{topics_li}</ul>
<p><strong>실습:</strong> {s.get('hands_on', '')}</p>
"""

    resources_rows = ""
    for r in resources:
        free = "🆓" if r.get("is_free") else "💰"
        resources_rows += f"""
<tr>
  <td>{r.get('stage', '')}</td>
  <td><a href="{r.get('url', '#')}">{r.get('title', '')}</a></td>
  <td>{r.get('type', '')}</td>
  <td>{free} {r.get('estimated_hours', '?')}h</td>
</tr>"""

    issues = "".join(
        f"<li>⚠️ {i}</li>" for i in validation_result.get("issues", [])
    )
    pass_icon = "✅" if passed else "❌"
    risk = validation_result.get("hallucination_risk", "unknown")

    return f"""
<h1>{curriculum.get('title', f'{topic} 학습 커리큘럼')}</h1>
<ac:structured-macro ac:name="panel">
  <ac:parameter ac:name="type">info</ac:parameter>
  <ac:rich-text-body>
    <p>
      <strong>수준:</strong> {depth} &nbsp;|&nbsp;
      <strong>총 학습 시간:</strong> {curriculum.get('total_duration_hours', '?')}시간 &nbsp;|&nbsp;
      <strong>생성일:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M')} &nbsp;|&nbsp;
      <strong>검증 점수:</strong> {score:.0%}
    </p>
  </ac:rich-text-body>
</ac:structured-macro>

<h2>📋 개요</h2>
<p>{curriculum.get('overview', '')}</p>

<h2>🎯 학습 목표</h2>
<ul>{objs_html}</ul>

{"<h2>⚙️ 사전 요구사항</h2><ul>" + prereqs + "</ul>" if prereqs else ""}

<h2>📚 커리큘럼</h2>
{stages_html}

<h2>🔗 참고 자료</h2>
<table>
  <tr>
    <th>Stage</th><th>자료</th><th>유형</th><th>비용/시간</th>
  </tr>
  {resources_rows}
</table>

<h2>✅ 검증 결과</h2>
<p><strong>통과 여부:</strong> {pass_icon} &nbsp;
   <strong>점수:</strong> {score:.0%} &nbsp;
   <strong>할루시네이션 위험도:</strong> {risk}</p>
<p>{validation_result.get('summary', '')}</p>
{"<ul>" + issues + "</ul>" if issues else ""}

<hr/>
<p><em>이 페이지는 AI 학습 자동화 시스템으로 자동 생성되었습니다.</em></p>
"""


class ConfluenceWriter:
    """Confluence REST API v2 를 통해 학습 커리큘럼 페이지를 생성한다."""

    def __init__(
        self,
        base_url: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
        space_id: str | None = None,
        parent_page_id: str | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("CONFLUENCE_BASE_URL", "")).rstrip("/")
        self.email = email or os.getenv("CONFLUENCE_EMAIL", "")
        self.api_token = api_token or os.getenv("CONFLUENCE_API_TOKEN", "")
        self.space_id = space_id or os.getenv("CONFLUENCE_SPACE_ID", "")
        self.parent_page_id = parent_page_id or os.getenv(
            "CONFLUENCE_PARENT_PAGE_ID", ""
        )
        self._configured = all(
            [self.base_url, self.email, self.api_token, self.space_id]
        )

    @property
    def _auth_header(self) -> str:
        token = base64.b64encode(
            f"{self.email}:{self.api_token}".encode()
        ).decode()
        return f"Basic {token}"

    async def create_page(
        self,
        topic: str,
        depth: str,
        curriculum: dict[str, Any],
        resources: list[dict[str, Any]],
        validation_result: dict[str, Any],
        markdown: str = "",
    ) -> str | None:
        """Confluence 페이지를 생성하고 page_id를 반환한다.

        실패 시 None을 반환하고 에러를 로깅한다 (graceful degradation).
        """
        if not self._configured:
            logger.warning("[ConfluenceWriter] 환경변수 미설정 — 페이지 생성 건너뜀")
            return None

        title = f"[AI Generated] {topic} 학습 커리큘럼 - {depth}"
        html_body = _to_html(topic, depth, curriculum, resources, validation_result)

        payload: dict[str, Any] = {
            "spaceId": self.space_id,
            "status": "current",
            "title": title,
            "body": {
                "representation": "storage",
                "value": html_body,
            },
        }
        if self.parent_page_id:
            payload["parentId"] = self.parent_page_id

        headers = {
            "Authorization": self._auth_header,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(headers=headers, timeout=30) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/api/v2/pages",
                    json=payload,
                )
                resp.raise_for_status()
                page_id = resp.json().get("id")
                logger.info("[ConfluenceWriter] 페이지 생성 완료 — id=%s", page_id)
                return page_id
            except httpx.HTTPError as e:
                logger.error("[ConfluenceWriter] 페이지 생성 실패: %s", e)
                return None
