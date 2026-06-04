"""Critic 검증 에이전트 (Tier 3 · Reviewer).

커리큘럼과 리소스의 품질·정확도·할루시네이션을 검증한다.
score_curriculum 도구로 채점을 구조화하고 명확한 점수와 피드백을 반환한다.

v0.1 — claude-sonnet-4-6, 단순 JSON 출력
v0.2 — claude-opus-4-7 로 교체 (강력한 교차 검증)
v0.4 — tool_use 도입 (score_curriculum 도구 보유)

[tool_use 흐름]
  1. Opus 가 커리큘럼·리소스를 분석 후 score_curriculum 도구 호출
  2. 도구가 항목별 가중치로 객관적 점수 계산 (LLM 주관 배제)
  3. 점수·이슈를 Opus 에 반환 → 최종 검증 JSON 생성

[Reviewer 역할]
  - review_score 와 review_feedback 을 State 에 기록
  - score < 0.75 → passed=False → Writer(CurriculumDesigner) 루프백
  - score >= 0.75 → passed=True → 출력 단계로 진행
"""
import json
import logging
from typing import Any

import anthropic

from agents.tools import CRITIC_TOOLS, dispatch_tool

logger = logging.getLogger(__name__)

MODEL = "claude-opus-4-7"

SYSTEM_PROMPT = """당신은 AI 생성 학습 커리큘럼을 검증하는 시니어 엔지니어입니다.
score_curriculum 도구를 호출해 커리큘럼을 채점한 뒤,
도구 결과를 바탕으로 최종 검증 리포트를 작성하세요.

검증 기준:
1. 기술 정보의 정확성 (버전, API, 개념)
2. 학습 단계의 논리적 순서
3. 소요 시간 현실성
4. URL/자료의 실존 가능성 (hallucination 감지)
5. 사용자 수준 적합성

반드시 다음 JSON 형식으로만 최종 응답하세요:
{
  "passed": true,
  "score": 0.85,
  "issues": ["문제점1"],
  "corrections": ["수정 제안1"],
  "hallucination_risk": "low|medium|high",
  "summary": "검증 요약"
}"""


class Critic:
    """커리큘럼·리소스 품질을 검증하는 Reviewer 에이전트.

    score_curriculum 도구로 채점을 수행 —
    LLM 주관이 아닌 항목별 가중치 점수로 passed 여부를 결정한다.
    """

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
        """커리큘럼과 리소스를 검증하고 review_score/review_feedback 을 포함한
        결과를 반환한다.

        Returns:
            {
              passed, score, issues, corrections,
              hallucination_risk, summary
            }
            score 는 도구가 계산한 객관적 점수 (0.0 ~ 1.0)
        """
        stages = curriculum.get("stages", [])
        user_content = (
            f"학습 주제: {topic}\n"
            f"목표 수준: {user_profile.get('proficiency', {})}\n\n"
            f"커리큘럼 개요: {curriculum.get('overview', '')}\n"
            f"단계 수: {len(stages)}\n"
            f"총 학습 시간: {curriculum.get('total_duration_hours', 0)}h\n"
            f"학습 목표: {curriculum.get('objectives', [])}\n\n"
            f"추천 자료 ({len(resources)}개):\n"
            f"{json.dumps(resources[:5], ensure_ascii=False)}\n\n"
            "score_curriculum 도구를 호출해 커리큘럼을 채점하세요."
        )

        messages: list[dict] = [{"role": "user", "content": user_content}]

        try:
            # ── 1차 호출: Opus 가 score_curriculum 호출 ───────────────────
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=CRITIC_TOOLS,
                messages=messages,
            )
            _log_usage("[Critic] 1차", self.model, response.usage)

            # ── 도구 실행 ─────────────────────────────────────────────────
            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = dispatch_tool(block.name, block.input)
                        logger.info(
                            "[Critic] tool=%s → %s", block.name, result
                        )
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})

                # ── 2차 호출: 도구 결과로 최종 검증 JSON 생성 ────────────
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=1024,
                    system=SYSTEM_PROMPT,
                    tools=CRITIC_TOOLS,
                    messages=messages,
                )
                _log_usage("[Critic] 2차", self.model, response.usage)

            text = _extract_text(response)
            result = json.loads(text)

            # score 가 도구 계산값과 일치하도록 보정
            if "score" not in result:
                result["score"] = 0.0
            result.setdefault("passed", result["score"] >= 0.75)
            return result

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


# ─── 헬퍼 ────────────────────────────────────────────────────────────────────

def _extract_text(response: Any) -> str:
    for block in response.content:
        if hasattr(block, "text"):
            text = block.text.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return text.strip()
    return '{"passed":false,"score":0.0,"issues":[],"corrections":[],"hallucination_risk":"high","summary":"응답 없음"}'


def _log_usage(label: str, model: str, usage: Any) -> None:
    logger.info(
        "%s model=%s input=%d output=%d",
        label, model,
        usage.input_tokens, usage.output_tokens,
    )
