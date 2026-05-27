"""커리큘럼 설계 에이전트 (Tier 2).

사용자 프로파일을 기반으로 단계별 학습 커리큘럼을 생성한다.
Sonnet 4.6 + Prompt Caching 적용 (시스템 프롬프트 캐싱).

v0.1 — claude-sonnet-4-6 (prompt caching)
"""
import json
import logging
from typing import Any, Literal

import anthropic

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

# prompt caching 대상: 긴 시스템 프롬프트
SYSTEM_PROMPT = """당신은 시니어 개발자 교육 전문가입니다.
사용자의 기술 프로파일과 학습 목표를 분석해
단계별 맞춤형 학습 커리큘럼을 설계합니다.

커리큘럼 설계 원칙:
1. 현재 수준에서 목표 수준까지 점진적 단계 구성
2. 각 단계는 명확한 학습 목표와 예상 소요 시간 포함
3. 실습 프로젝트와 이론 학습의 균형 유지
4. 공식 문서·검증된 자료 우선 참조
5. 이전 학습 이력과의 중복 최소화

반드시 다음 JSON 형식으로만 응답하세요:
{
  "title": "커리큘럼 제목",
  "overview": "전체 개요 (2-3문장)",
  "objectives": ["학습 목표1", "학습 목표2"],
  "stages": [
    {
      "stage": 1,
      "title": "단계 제목",
      "duration_hours": 10,
      "topics": ["주제1", "주제2"],
      "hands_on": "실습 프로젝트 설명",
      "milestone": "완료 기준"
    }
  ],
  "total_duration_hours": 30,
  "prerequisites": ["사전 지식1"]
}"""


class CurriculumDesigner:
    """사용자 프로파일 기반 학습 커리큘럼을 설계한다.

    Sonnet 4.6 + Prompt Caching으로 시스템 프롬프트 반복 비용을 절감한다.
    """

    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        self.client = client or anthropic.Anthropic()
        self.model = MODEL

    def design(
        self,
        topic: str,
        depth: Literal["beginner", "intermediate", "advanced"],
        user_profile: dict[str, Any],
    ) -> dict[str, Any]:
        """학습 커리큘럼을 설계한다.

        Args:
            topic: 학습 주제
            depth: 목표 수준
            user_profile: Tier 1 산출물

        Returns:
            curriculum dict
        """
        user_content = f"""
학습 주제: {topic}
목표 수준: {depth}

사용자 프로파일:
{json.dumps(user_profile, ensure_ascii=False, indent=2)}

위 프로파일을 기반으로 {depth} 수준의 {topic} 학습 커리큘럼을 설계하세요.
기존 학습 이력({user_profile.get('learning_history', [])})과 중복되는 내용은 최소화하세요.
"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        # Prompt Caching: 시스템 프롬프트 캐싱
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_content}],
            )
            usage = response.usage
            cache_read = getattr(usage, "cache_read_input_tokens", 0)
            cache_write = getattr(usage, "cache_creation_input_tokens", 0)
            logger.info(
                "[CurriculumDesigner] model=%s input=%d output=%d "
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
            return json.loads(text)
        except (json.JSONDecodeError, anthropic.APIError) as e:
            logger.error("[CurriculumDesigner] 오류: %s", e)
            return {
                "title": f"{topic} 학습 커리큘럼",
                "overview": f"{depth} 수준의 {topic} 학습 커리큘럼",
                "objectives": [f"{topic} 핵심 개념 이해"],
                "stages": [
                    {
                        "stage": 1,
                        "title": "기초",
                        "duration_hours": 10,
                        "topics": [topic],
                        "hands_on": "기본 예제 구현",
                        "milestone": "Hello World 수준 구현",
                    }
                ],
                "total_duration_hours": 10,
                "prerequisites": [],
            }
