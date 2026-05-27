"""LangGraph 파이프라인 공유 상태 정의."""
from typing import Literal, TypedDict


class LearningState(TypedDict):
    """멀티 에이전트 파이프라인 전체 공유 상태."""

    # --- 입력 ---
    topic: str
    depth: Literal["beginner", "intermediate", "advanced"]

    # --- 수집 데이터 ---
    github_data: dict | None        # GitHub 활동 (repos, 언어, 커밋 요약)
    confluence_history: list | None  # 기존 Confluence 페이지 목록

    # --- Tier 1 산출물 (Haiku / Sonnet) ---
    user_profile: dict | None       # 기술 스택, 숙련도, 학습 이력

    # --- Tier 2 산출물 (Sonnet) ---
    curriculum: dict | None         # 단계별 학습 커리큘럼
    resources: list | None          # 큐레이션된 참고 자료

    # --- Tier 3 산출물 (Opus / Sonnet) ---
    validation_result: dict | None  # { passed: bool, issues: list[str], score: float }

    # --- 파이프라인 제어 ---
    retry_count: int

    # --- 최종 출력 ---
    final_markdown: str | None
    confluence_page_id: str | None
    errors: list[str]
