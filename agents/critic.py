"""Critic 검증 에이전트 (Tier 3).

커리큘럼과 리소스의 품질·정확도·할루시네이션을 검증한다.

v0.1 — claude-sonnet-4-6 사용
v0.2 — claude-opus-4-7 로 교체 (강력한 교차 검증)
"""
import json
import logging
from typing import Any

import anthropic

logger = logging.getLogger(__name__)

# v0.1: Sonnet 사용 (v0.2 에서 Opus로 교체)
MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """당신은 AI가 생성한 학습 커리큘럼을 검증하는 시니어 엔지니어입니다.
커리큘럼의 기술적 정확성, 할루시네이션 여부, 자료 신뢰도를 엄격히 검토합니다.

검증 기준:
1. 기술 정보의 정확성 (버전, API, 개념)
2. 학습 단계의 논리적 순서
3. 소요 시간 현실성
4. URL/자료의 실존 가능성 (hallucination 감지)
5. 사용자 수준 적합성

반드시 다음 JSON 형식으로만 응답하세요:
{
  "passed": true,
  "score": 0.85,
  "issues": ["문제점1", "문제점2"],
  "corrections": ["수정 제안1"],
  "hallucination_risk": "low|medium|high",
  "summary": "검증 요약"
}"""


class Critic:
    """커리큘럼·리소스 품질을 검증하는 Critic 에이전트."""

    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        self.client = client or anthropic.Anthropic()
        self.model = MODEL

    def validate(
        self,
        topic: str,
        curriculum: dict[str, Any],
        resources: list[dict[str, Any]],
        user_profile: dict[str, Any],
    ) -> dict[str, Any]:
        """커리큘럼과 리소스를 검증한다.

        Args:
            topic: 학습 주제
            curriculum: Tier 2 커리큘럼
            resources: Tier 2 큐레이션 자료
            user_profile: Tier 1 프로파일

        Returns:
            validation_result dict with { passed, score, issues, corrections,
                                          hallucination_risk, summary }
        """
        user_content = f"""
학습 주제: {topic}
사용자 프로파일: {json.dumps(user_profile, ensure_ascii=False)}

커리큘럼:
{json.dumps(curriculum, ensure_ascii=False, indent=2)}

추천 자료 ({len(resources)}개):
{json.dumps(resources[:10], ensure_ascii=False, indent=2)}

위 커리큘럼과 자료의 품질을 엄격히 검증하세요.
특히 기술적 오류, 잘못된 URL, 비현실적인 학습 시간을 중점적으로 확인하세요.
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
                "[Critic] model=%s input_tokens=%d output_tokens=%d",
                self.model,
                usage.input_tokens,
                usage.output_tokens,
            )
            text = response.content[0].text.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
        except (json.JSONDecodeError, anthropic.APIError) as e:
            logger.error("[Critic] 오류: %s", e)
            return {
                "passed": False,
                "score": 0.0,
                "issues": [f"검증 오류: {e}"],
                "corrections": [],
                "hallucination_risk": "high",
                "summary": "검증 실패",
            }
