"""에이전트별 독립 도구 정의 + 로컬 실행 로직.

각 에이전트는 자신의 역할에 맞는 도구만 보유한다.

  ProfileAnalyzer  → classify_tech_stack   (분류·태깅)
  CurriculumDesigner → estimate_duration    (학습 시간 추정)
                     → apply_critic_feedback (피드백 반영)
  Critic           → score_curriculum       (품질 채점)

도구 실행 흐름:
  1. 에이전트가 tools= 파라미터로 도구 목록을 LLM에 전달
  2. LLM이 tool_use 블록으로 호출 의사를 표현
  3. 우리 코드가 로컬에서 실행하고 tool_result로 반환
  4. LLM이 결과를 보고 최종 응답 생성
"""
from __future__ import annotations

import json
from typing import Any

# ─── ProfileAnalyzer 도구 ─────────────────────────────────────────────────────

PROFILE_TOOLS: list[dict] = [
    {
        "name": "classify_tech_stack",
        "description": (
            "GitHub 데이터(언어별 코드량·커밋 키워드)로 기술 스택을 분류하고 "
            "숙련도 수준을 평가한다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "languages": {
                    "type": "object",
                    "description": "언어별 코드 바이트 수. 예: {\"Python\": 8000}",
                },
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "커밋 메시지·레포 설명에서 추출한 기술 키워드",
                },
                "topic": {
                    "type": "string",
                    "description": "학습 목표 주제",
                },
            },
            "required": ["languages", "topic"],
        },
    }
]

# ─── CurriculumDesigner 도구 ──────────────────────────────────────────────────

CURRICULUM_TOOLS: list[dict] = [
    {
        "name": "estimate_duration",
        "description": (
            "주제·수준·현재 기술 스택을 고려해 각 단계별 현실적인 학습 시간(시간)을 추정한다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "depth": {
                    "type": "string",
                    "enum": ["beginner", "intermediate", "advanced"],
                },
                "stage_count": {
                    "type": "integer",
                    "description": "커리큘럼 단계 수",
                },
                "has_prior_knowledge": {
                    "type": "boolean",
                    "description": "사용자가 관련 사전 지식을 보유하는가",
                },
            },
            "required": ["topic", "depth", "stage_count"],
        },
    },
    {
        "name": "apply_critic_feedback",
        "description": (
            "Critic 에이전트가 반환한 검증 실패 피드백을 분석하고 "
            "커리큘럼 개선 방향을 구조화한다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "issues": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Critic이 발견한 문제 목록",
                },
                "corrections": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Critic의 수정 지시사항",
                },
                "score": {
                    "type": "number",
                    "description": "이전 검증 점수 (0.0 ~ 1.0)",
                },
            },
            "required": ["issues"],
        },
    },
]

# ─── Critic 도구 ──────────────────────────────────────────────────────────────

CRITIC_TOOLS: list[dict] = [
    {
        "name": "score_curriculum",
        "description": (
            "커리큘럼의 품질 항목을 평가해 0.0~1.0 점수를 계산하고 "
            "통과 여부를 판정한다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "has_clear_objectives": {
                    "type": "boolean",
                    "description": "학습 목표가 명확하게 정의되어 있는가",
                },
                "stage_count": {
                    "type": "integer",
                    "description": "커리큘럼 단계 수",
                },
                "total_hours": {
                    "type": "number",
                    "description": "총 학습 시간",
                },
                "hours_realistic": {
                    "type": "boolean",
                    "description": "학습 시간이 현실적인가",
                },
                "depth_match": {
                    "type": "boolean",
                    "description": "커리큘럼이 목표 수준(beginner/intermediate/advanced)에 맞는가",
                },
                "has_hands_on": {
                    "type": "boolean",
                    "description": "실습 프로젝트가 포함되어 있는가",
                },
                "issues_found": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "발견된 문제 목록 (없으면 빈 배열)",
                },
                "hallucination_risk": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "기술 정보 hallucination 위험도",
                },
            },
            "required": [
                "has_clear_objectives",
                "stage_count",
                "total_hours",
                "hours_realistic",
                "depth_match",
                "has_hands_on",
                "issues_found",
                "hallucination_risk",
            ],
        },
    }
]


# ─── 로컬 도구 실행 함수 ──────────────────────────────────────────────────────

def execute_classify_tech_stack(tool_input: dict[str, Any]) -> str:
    """classify_tech_stack 도구를 로컬에서 실행한다."""
    languages: dict[str, int] = tool_input.get("languages", {})
    keywords: list[str] = tool_input.get("keywords", [])
    topic: str = tool_input.get("topic", "")

    # 언어별 비중으로 숙련도 추정
    total_bytes = sum(languages.values()) or 1
    proficiency: dict[str, str] = {}
    for lang, nbytes in sorted(languages.items(), key=lambda x: x[1], reverse=True):
        ratio = nbytes / total_bytes
        proficiency[lang] = (
            "advanced" if ratio > 0.6
            else "intermediate" if ratio > 0.25
            else "beginner"
        )

    top_langs = list(proficiency.keys())[:5]

    # 주제 친숙도 감지
    topic_lower = topic.lower()
    topic_familiar = any(
        topic_lower in kw.lower() or kw.lower() in topic_lower
        for kw in keywords
    )

    # 스택 유형 추론
    backend = {"Python", "Java", "Go", "Rust", "Ruby", "PHP", "C#", "Kotlin"}
    frontend = {"JavaScript", "TypeScript", "CSS", "HTML", "Vue", "React"}
    has_be = any(l in backend for l in top_langs)
    has_fe = any(l in frontend for l in top_langs)
    stack_type = (
        "fullstack" if has_be and has_fe
        else "backend" if has_be
        else "frontend" if has_fe
        else "general"
    )

    return json.dumps(
        {
            "top_languages": top_langs,
            "proficiency": proficiency,
            "stack_type": stack_type,
            "topic_familiarity": "experienced" if topic_familiar else "new_topic",
        },
        ensure_ascii=False,
    )


def execute_estimate_duration(tool_input: dict[str, Any]) -> str:
    """estimate_duration 도구를 로컬에서 실행한다."""
    depth: str = tool_input.get("depth", "intermediate")
    stage_count: int = tool_input.get("stage_count", 3)
    has_prior: bool = tool_input.get("has_prior_knowledge", False)

    base_hours = {"beginner": 12, "intermediate": 20, "advanced": 30}.get(depth, 20)
    if has_prior:
        base_hours = int(base_hours * 0.7)

    hours_per_stage = round(base_hours / max(stage_count, 1), 1)

    return json.dumps(
        {
            "total_hours": base_hours,
            "hours_per_stage": hours_per_stage,
            "note": f"{depth} 수준 기준, 사전 지식 {'있음' if has_prior else '없음'}",
        },
        ensure_ascii=False,
    )


def execute_apply_critic_feedback(tool_input: dict[str, Any]) -> str:
    """apply_critic_feedback 도구를 로컬에서 실행한다."""
    issues: list[str] = tool_input.get("issues", [])
    corrections: list[str] = tool_input.get("corrections", [])
    score: float = tool_input.get("score", 0.0)

    improvement_plan = []
    for i, issue in enumerate(issues):
        fix = corrections[i] if i < len(corrections) else "해당 항목 전면 재작성"
        improvement_plan.append({"problem": issue, "action": fix})

    return json.dumps(
        {
            "previous_score": score,
            "improvement_count": len(improvement_plan),
            "improvement_plan": improvement_plan,
            "priority": "high" if score < 0.5 else "medium",
        },
        ensure_ascii=False,
    )


def execute_score_curriculum(tool_input: dict[str, Any]) -> str:
    """score_curriculum 도구를 로컬에서 실행한다."""
    # 항목별 가중치 채점
    score = 0.0
    score += 0.20 if tool_input.get("has_clear_objectives") else 0.0
    score += 0.15 if tool_input.get("hours_realistic") else 0.0
    score += 0.20 if tool_input.get("depth_match") else 0.0
    score += 0.15 if tool_input.get("has_hands_on") else 0.0

    stage_count: int = tool_input.get("stage_count", 0)
    score += 0.15 if 2 <= stage_count <= 8 else 0.05

    risk = tool_input.get("hallucination_risk", "high")
    score += {"low": 0.15, "medium": 0.08, "high": 0.0}.get(risk, 0.0)

    issues: list[str] = tool_input.get("issues_found", [])
    score = max(0.0, score - len(issues) * 0.05)

    return json.dumps(
        {
            "score": round(score, 2),
            "passed": score >= 0.75,
            "hallucination_risk": risk,
            "issues": issues,
        },
        ensure_ascii=False,
    )


# ─── 디스패처 ─────────────────────────────────────────────────────────────────

TOOL_EXECUTORS = {
    "classify_tech_stack": execute_classify_tech_stack,
    "estimate_duration": execute_estimate_duration,
    "apply_critic_feedback": execute_apply_critic_feedback,
    "score_curriculum": execute_score_curriculum,
}


def dispatch_tool(tool_name: str, tool_input: dict[str, Any]) -> str:
    """도구 이름으로 실행 함수를 찾아 호출한다."""
    executor = TOOL_EXECUTORS.get(tool_name)
    if executor is None:
        return json.dumps({"error": f"unknown tool: {tool_name}"})
    return executor(tool_input)
