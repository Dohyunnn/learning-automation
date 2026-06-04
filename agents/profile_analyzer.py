"""프로필 분석 에이전트 (Tier 1).

GitHub 데이터와 Confluence 이력을 바탕으로 사용자 기술 스택·숙련도 프로파일을 생성한다.

v0.1 — claude-sonnet-4-6, 단순 JSON 출력
v0.3 — claude-haiku-4-5 로 교체 (빠른 분류·태깅)
v0.4 — tool_use 패턴 도입 (classify_tech_stack 도구 보유)

[tool_use 흐름]
  1. Haiku 에게 classify_tech_stack 도구와 함께 GitHub 데이터 전달
  2. Haiku 가 tool_use 블록으로 분류 파라미터를 결정
  3. 로컬 execute_classify_tech_stack() 가 실제 분류 수행
  4. tool_result 를 다시 Haiku 에 전달 → 최종 프로파일 JSON 생성
"""
import json
import logging
from typing import Any

import anthropic

from agents.tools import PROFILE_TOOLS, dispatch_tool

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5"

SYSTEM_PROMPT = """당신은 개발자 프로파일 분석 전문가입니다.
classify_tech_stack 도구를 호출해 기술 스택을 분류한 뒤,
도구 결과를 바탕으로 최종 프로파일 JSON을 생성하세요.

최종 응답은 반드시 아래 JSON 형식만 사용하세요:
{
  "tech_stack": ["기술1", "기술2"],
  "proficiency": {"기술1": "beginner|intermediate|advanced"},
  "learning_history": ["주제1"],
  "interests": ["관심분야1"],
  "gaps": ["부족한 영역1"]
}"""


class ProfileAnalyzer:
    """GitHub + Confluence 데이터로 사용자 프로파일을 분석한다.

    tool_use 패턴:
      Haiku 가 classify_tech_stack 도구를 호출 →
      로컬 실행 결과를 다시 전달 →
      Haiku 가 최종 프로파일 JSON 생성
    """

    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        self.client = client or anthropic.Anthropic()
        self.model = MODEL

    def analyze(
        self,
        topic: str,
        github_data: dict[str, Any],
        confluence_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """tool_use 패턴으로 프로파일 분석을 수행한다."""

        # 커밋 메시지에서 기술 키워드 추출
        keywords: list[str] = []
        for repo in github_data.get("repos", []):
            keywords.extend(repo.get("recent_commits", []))
            if repo.get("description"):
                keywords.append(repo["description"])

        # Confluence 이력 제목도 키워드로
        keywords += [p.get("title", "") for p in confluence_history[:10]]

        user_content = (
            f"학습 주제: {topic}\n\n"
            f"GitHub 언어 데이터: {json.dumps(github_data.get('top_languages', []))}\n"
            f"언어별 코드량 (집계): "
            f"{json.dumps(_aggregate_languages(github_data), ensure_ascii=False)}\n"
            f"기술 키워드: {json.dumps(keywords[:20], ensure_ascii=False)}\n\n"
            "classify_tech_stack 도구를 호출해 기술 스택을 분류하세요."
        )

        messages: list[dict] = [{"role": "user", "content": user_content}]

        try:
            # ── 1차 호출: LLM이 도구 호출 결정 ──────────────────────────
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=PROFILE_TOOLS,
                messages=messages,
            )
            _log_usage("[ProfileAnalyzer] 1차", self.model, response.usage)

            # ── 도구 호출 처리 ────────────────────────────────────────────
            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = dispatch_tool(block.name, block.input)
                        logger.info(
                            "[ProfileAnalyzer] tool=%s input=%s",
                            block.name, block.input,
                        )
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                # ── 2차 호출: 도구 결과를 받아 최종 응답 생성 ────────────
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})

                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=1024,
                    system=SYSTEM_PROMPT,
                    tools=PROFILE_TOOLS,
                    messages=messages,
                )
                _log_usage("[ProfileAnalyzer] 2차", self.model, response.usage)

            # ── 최종 JSON 파싱 ────────────────────────────────────────────
            text = _extract_text(response)
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


# ─── 헬퍼 ────────────────────────────────────────────────────────────────────

def _aggregate_languages(github_data: dict[str, Any]) -> dict[str, int]:
    """레포별 언어 데이터를 합산한다."""
    total: dict[str, int] = {}
    for repo in github_data.get("repos", []):
        for lang, nbytes in repo.get("languages", {}).items():
            total[lang] = total.get(lang, 0) + nbytes
    return total


def _extract_text(response: Any) -> str:
    """응답에서 텍스트 블록을 추출하고 JSON 펜스를 제거한다."""
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
