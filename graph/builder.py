"""LangGraph StateGraph 빌더.

파이프라인 흐름:
  collect_github ──┐
                   ├─→ analyze_profile
  collect_confluence ──┘
        ↓
  design_curriculum
        ↓
  curate_resources
        ↓
  validate ──→ [route_after_validation]
    ├── "write"     → write_markdown → write_confluence
    ├── "retry"     → handle_retry  → design_curriculum (재진입)
    └── "max_retry" → handle_max_retry → END
"""
import logging

from langgraph.graph import END, START, StateGraph

from graph.nodes import (
    analyze_profile,
    collect_confluence,
    collect_github,
    curate_resources,
    design_curriculum,
    handle_max_retry,
    handle_retry,
    route_after_validation,
    validate,
    write_confluence,
    write_markdown,
)
from graph.state import LearningState

logger = logging.getLogger(__name__)


def build_graph() -> StateGraph:
    """LearningState 기반 LangGraph StateGraph를 빌드한다."""
    graph = StateGraph(LearningState)

    # ── 노드 등록 ──────────────────────────────────────────────────────────
    graph.add_node("collect_github", collect_github)
    graph.add_node("collect_confluence", collect_confluence)
    graph.add_node("analyze_profile", analyze_profile)
    graph.add_node("design_curriculum", design_curriculum)
    graph.add_node("curate_resources", curate_resources)
    graph.add_node("validate", validate)
    graph.add_node("write_markdown", write_markdown)
    graph.add_node("write_confluence", write_confluence)
    graph.add_node("handle_retry", handle_retry)
    graph.add_node("handle_max_retry", handle_max_retry)

    # ── 엣지 정의 ──────────────────────────────────────────────────────────
    # 데이터 수집 (병렬 → 프로파일 분석)
    graph.add_edge(START, "collect_github")
    graph.add_edge(START, "collect_confluence")
    graph.add_edge("collect_github", "analyze_profile")
    graph.add_edge("collect_confluence", "analyze_profile")

    # Tier 1 → Tier 2
    graph.add_edge("analyze_profile", "design_curriculum")
    graph.add_edge("design_curriculum", "curate_resources")
    graph.add_edge("curate_resources", "validate")

    # Tier 3 조건부 라우팅
    graph.add_conditional_edges(
        "validate",
        route_after_validation,
        {
            "write": "write_markdown",
            "retry": "handle_retry",
            "max_retry": "handle_max_retry",
        },
    )

    # 재시도: 커리큘럼 재설계로 회귀
    graph.add_edge("handle_retry", "design_curriculum")

    # 최대 재시도 초과 → 종료
    graph.add_edge("handle_max_retry", END)

    # 출력 (순차)
    graph.add_edge("write_markdown", "write_confluence")
    graph.add_edge("write_confluence", END)

    return graph


def compile_graph():
    """컴파일된 실행 가능한 그래프를 반환한다."""
    graph = build_graph()
    compiled = graph.compile()
    logger.info("[Graph] 파이프라인 컴파일 완료")
    return compiled
