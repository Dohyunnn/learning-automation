"""프로필 분석 에이전트 (Tier 1).

GitHub 데이터와 Confluence 이력을 바탕으로 사용자 기술 스택·숙련도 프로파일을 생성한다.

v0.1 — claude-sonnet-4-6 사용
v0.3 — claude-haiku-4-5 로 교체 (빠른 분류·태깅, 비용 절감)
"""
import json
import logging
from typing import Any

import anthropic

logger = logging.getLogger(__name__)

# v0.1: 단일 Sonnet 모델
MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """당신은 개발자 프로파일 분석 전문가입니다.
GitHub 저장소 데이터와 Confluence 학습 이력을 분석해
사용자의 기술 스택, 숙련도 수준, 학습 이력, 관심 분야를 JSON으로 정리합니다.

반드시 다음 JSON 형식으로만 응답하세요:
{
  "tech_stack": ["기술1", "기술2"],
  "proficiency": {"기술1": "beginner|intermediate|advanced"},
  "learning_history": ["주제1", "주제2"],
  "interests": ["관심분야1"],
  "gaps": ["부족한 영역1"]
}"""


class ProfileAnalyzer:
    """GitHub + Confluence 데이터로 사용자 프로파일을 분석한다."""

    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        self.client = client or anthropic.Anthropic()
        self.model = MODEL

    def analyze(
        self,
        topic: str,
        github_data: dict[str, Any],
        confluence_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """프로파일 분석을 수행한다.

        Args:
            topic: 학습 목표 주제
            github_data: GitHub 활동 데이터
            confluence_history: Confluence 기존 페이지 목록

        Returns:
            user_profile dict
        """
        user_content = f"""
학습 주제: {topic}

GitHub 데이터:
{json.dumps(github_data, ensure_ascii=False, indent=2)}

Confluence 학습 이력 (최근 {len(confluence_history)}개 페이지):
{json.dumps(confluence_history[:10], ensure_ascii=False, indent=2)}

위 정보를 분석해 사용자 프로파일을 생성하세요.
"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
            usage = response.usage
            logger.info(
                "[ProfileAnalyzer] model=%s input_tokens=%d output_tokens=%d",
                self.model,
                usage.input_tokens,
                usage.output_tokens,
            )
            text = response.content[0].text.strip()
            # JSON 블록 파싱
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
        except (json.JSONDecodeError, anthropic.APIError) as e:
            logger.error("[ProfileAnalyzer] 오류: %s", e)
            return {
                "tech_stack": github_data.get("top_languages", []),
                "proficiency": {},
                "learning_history": [],
                "interests": [topic],
                "gaps": [],
            }
