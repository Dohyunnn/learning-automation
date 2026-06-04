"""LangGraph 파이프라인 공유 상태 정의."""
from typing import Literal, TypedDict


class LearningState(TypedDict):
    """멀티 에이전트 파이프라인 전체 공유 상태.

    State 기반 흐름 관리:
      - review_score / review_feedback 로 Writer ↔ Reviewer 루프를 제어
      - retry_count 로 최대 재시도(2회)를 강제해 무한 루프 방지
      - 각 필드는 해당 Tier 에이전트만 기록 권한을 가짐
    """

    # --- 입력 ---
    topic: str
    depth: Literal["beginner", "intermediate", "advanced"]

    # --- 수집 데이터 ---
    github_data: dict | None         # GitHub 활동 (repos, 언어, 커밋 요약)
    confluence_history: list | None  # 기존 Confluence 페이지 목록

    # --- Tier 1 산출물 (Haiku) ---
    user_profile: dict | None        # 기술 스택, 숙련도, 학습 이력

    # --- Tier 2 산출물 (Sonnet) ---
    curriculum: dict | None          # 단계별 학습 커리큘럼
    resources: list | None           # 큐레이션된 참고 자료

    # --- Tier 3 산출물 (Opus) — Reviewer ↔ Writer 루프 제어 ---
    validation_result: dict | None   # 전체 검증 결과 raw dict
    review_score: float | None       # Critic이 채점한 품질 점수 (0.0 ~ 1.0)
    review_feedback: str | None      # Critic의 피드백 요약 (재시도 시 Writer에 전달)

    # --- 파이프라인 제어 ---
    retry_count: int                 # Writer 재호출 횟수 (최대 2 → max_retry 종료)

    # --- 최종 출력 ---
    final_markdown: str | None
    confluence_page_id: str | None
    errors: list[str]
