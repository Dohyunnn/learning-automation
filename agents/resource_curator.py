"""리소스 큐레이션 에이전트 (Tier 2).

커리큘럼 단계별로 학습 자료(공식 문서, 튜토리얼, 예제)를 큐레이션한다.
Sonnet 4.6 + Prompt Caching 적용.

v0.1 — claude-sonnet-4-6 (prompt caching)
"""
import json
import logging
from typing import Any

import anthropic

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """당신은 개발자 학습 자료 큐레이터입니다.
커리큘럼 각 단계에 가장 적합한 학습 자료를 추천합니다.

큐레이션 기준:
1. 공식 문서를 최우선으로 참조
2. 무료 자료를 유료 자료보다 우선
3. 실습 예제가 포함된 자료 선호
4. 최신 버전 기준 자료 우선

반드시 다음 JSON 형식으로만 응답하세요:
{
  "resources": [
    {
      "stage": 1,
      "title": "자료 제목",
      "type": "official_docs|tutorial|video|book|github",
      "url": "https://...",
      "description": "자료 설명",
      "estimated_hours": 2,
      "is_free": true
    }
  ]
}"""


class ResourceCurator:
    """커리큘럼 기반 학습 자료를 큐레이션한다."""

    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        self.client = client or anthropic.Anthropic()
        self.model = MODEL

    def curate(
        self,
        topic: str,
        curriculum: dict[str, Any],
        user_profile: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """커리큘럼 기반 학습 자료를 큐레이션한다.

        Args:
            topic: 학습 주제
            curriculum: Tier 2 커리큘럼 산출물
            user_profile: Tier 1 프로파일

        Returns:
            resources list
        """
        stages_summary = json.dumps(
            curriculum.get("stages", []), ensure_ascii=False, indent=2
        )
        user_content = f"""
학습 주제: {topic}
사용자 수준: {user_profile.get('proficiency', {})}

커리큘럼 단계:
{stages_summary}

각 단계에 맞는 학습 자료를 추천하세요.
공식 문서와 실습 자료를 균형 있게 포함하세요.
"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_content}],
            )
            usage = response.usage
            cache_read = getattr(usage, "cache_read_input_tokens", 0)
            cache_write = getattr(usage, "cache_creation_input_tokens", 0)
            logger.info(
                "[ResourceCurator] model=%s input=%d output=%d "
                "cache_read=%d cache_write=%d",
                self.model,
                usage.input_tokens,
                usage.output_tokens,
                cache_read,
                cache_write,
            )
            text = response.content[0].text.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text)
            return data.get("resources", [])
        except (json.JSONDecodeError, anthropic.APIError) as e:
            logger.error("[ResourceCurator] 오류: %s", e)
            return [
                {
                    "stage": 1,
                    "title": f"{topic} 공식 문서",
                    "type": "official_docs",
                    "url": f"https://docs.{topic.lower().replace(' ', '')}.dev",
                    "description": "공식 문서",
                    "estimated_hours": 5,
                    "is_free": True,
                }
            ]
