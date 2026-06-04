"""커리큘럼 설계 에이전트 (Tier 2 · Writer).

사용자 프로파일 기반으로 단계별 학습 커리큘럼을 생성한다.
Critic(Reviewer) 실패 시 피드백을 받아 재작성한다 (Writer 루프).

v0.1 — Sonnet, 단순 JSON 출력
v0.4 — tool_use 도입 + Critic 피드백 기반 재작성 루프

[tool_use 흐름]
  1. estimate_duration 으로 현실적 학습 시간 계산
  2. (재시도 시) apply_critic_feedback 으로 이전 실패 원인 구조화
  3. 도구 결과 + 프로파일로 최종 커리큘럼 JSON 생성

[Writer ↔ Reviewer 루프]
  - critic_feedback 파라미터가 있으면 재작성 모드로 동작
  - 피드백의 improvement_plan 을 시스템 프롬프트에 주입
  - retry_count 는 graph/nodes.py 의 handle_retry 가 관리
"""
import json
import logging
from typing import Any, Literal

import anthropic

from agents.tools import CURRICULUM_TOOLS, dispatch_tool

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

_BASE_SYSTEM = """당신은 시니어 개발자 교육 전문가입니다.
estimate_duration 도구로 현실적인 학습 시간을 먼저 계산한 뒤,
단계별 맞춤형 학습 커리큘럼을 설계합니다.

커리큘럼 설계 원칙:
1. 현재 수준에서 목표 수준까지 점진적 단계 구성
2. 각 단계는 명확한 학습 목표와 예상 소요 시간 포함
3. 실습 프로젝트와 이론 학습의 균형 유지
4. 공식 문서·검증된 자료 우선 참조
5. 이전 학습 이력과의 중복 최소화

반드시 다음 JSON 형식으로만 최종 응답하세요:
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

_RETRY_ADDENDUM = """
⚠️ [재작성 모드] Reviewer(Critic) 검증 실패로 재호출되었습니다.
apply_critic_feedback 도구를 먼저 호출해 개선 계획을 수립한 뒤 커리큘럼을 재작성하세요.

반드시 이전 문제점을 해결해야 합니다. 같은 실수를 반복하지 마세요.
"""


class CurriculumDesigner:
    """사용자 프로파일 기반 학습 커리큘럼을 설계한다.

    Sonnet 4.6 + Prompt Caching + tool_use.
    Critic 실패 시 critic_feedback 를 받아 재작성 (Writer 루프).
    """

    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        self.client = client or anthropic.Anthropic()
        self.model = MODEL

    def design(
        self,
        topic: str,
        depth: Literal["beginner", "intermediate", "advanced"],
        user_profile: dict[str, Any],
        critic_feedback: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """학습 커리큘럼을 설계한다.

        Args:
            topic: 학습 주제
            depth: 목표 수준
            user_profile: Tier 1 프로파일
            critic_feedback: Critic 실패 시 전달되는 피드백 dict
                             { passed, score, issues, corrections, ... }

        Returns:
            curriculum dict
        """
        is_retry = critic_feedback is not None
        system_text = _BASE_SYSTEM + (_RETRY_ADDENDUM if is_retry else "")

        # Prompt Caching — 시스템 프롬프트 캐싱
        system = [{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}]

        # 사용자 메시지 구성
        feedback_section = _format_feedback(critic_feedback) if is_retry else ""
        user_content = (
            f"학습 주제: {topic}\n"
            f"목표 수준: {depth}\n\n"
            f"사용자 프로파일:\n"
            f"{json.dumps(user_profile, ensure_ascii=False, indent=2)}\n"
            f"{feedback_section}\n"
            f"estimate_duration 도구를 호출해 학습 시간을 추정한 뒤 커리큘럼을 설계하세요."
        )

        messages: list[dict] = [{"role": "user", "content": user_content}]

        try:
            # ── 도구 호출 루프 (최대 2회 턴) ─────────────────────────────
            for turn in range(3):
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=2048,
                    system=system,
                    tools=CURRICULUM_TOOLS,
                    messages=messages,
                )
                _log_usage(f"[CurriculumDesigner] turn={turn}", self.model, response.usage)

                if response.stop_reason != "tool_use":
                    break  # 도구 호출 없음 → 최종 응답

                # 도구 실행
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = dispatch_tool(block.name, block.input)
                        logger.info(
                            "[CurriculumDesigner] tool=%s input=%s",
                            block.name, block.input,
                        )
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})

            text = _extract_text(response)
            return json.loads(text)

        except (json.JSONDecodeError, anthropic.APIError) as e:
            logger.error("[CurriculumDesigner] 오류: %s", e)
            return _fallback_curriculum(topic, depth)


# ─── 헬퍼 ────────────────────────────────────────────────────────────────────

def _format_feedback(feedback: dict[str, Any]) -> str:
    """Critic 피드백을 프롬프트용 텍스트로 포맷한다."""
    issues = feedback.get("issues", [])
    corrections = feedback.get("corrections", [])
    score = feedback.get("score", 0.0)

    lines = [
        f"\n이전 검증 점수: {score:.0%}",
        "\n[Reviewer 발견 문제]",
    ]
    for i, issue in enumerate(issues):
        fix = corrections[i] if i < len(corrections) else "(재작성 필요)"
        lines.append(f"  - 문제: {issue}")
        lines.append(f"    수정: {fix}")
    return "\n".join(lines)


def _extract_text(response: Any) -> str:
    for block in response.content:
        if hasattr(block, "text"):
            text = block.text.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return text.strip()
    return "{}"


def _log_usage(label: str, model: str, usage: Any) -> None:
    logger.info(
        "%s model=%s input=%d output=%d cache_read=%d cache_write=%d",
        label, model,
        usage.input_tokens, usage.output_tokens,
        getattr(usage, "cache_read_input_tokens", 0),
        getattr(usage, "cache_creation_input_tokens", 0),
    )


def _fallback_curriculum(topic: str, depth: str) -> dict[str, Any]:
    return {
        "title": f"{topic} 학습 커리큘럼",
        "overview": f"{depth} 수준의 {topic} 학습 커리큘럼",
        "objectives": [f"{topic} 핵심 개념 이해"],
        "stages": [{
            "stage": 1, "title": "기초",
            "duration_hours": 10, "topics": [topic],
            "hands_on": "기본 예제 구현", "milestone": "기초 구현",
        }],
        "total_duration_hours": 10,
        "prerequisites": [],
    }
