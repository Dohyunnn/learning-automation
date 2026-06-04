"""LangGraph 파이프라인 노드 함수 정의."""
import logging
from typing import Any

from graph.state import LearningState

logger = logging.getLogger(__name__)


# ─── Tier 1: 데이터 수집 ─────────────────────────────────────────────────────

async def collect_github(state: LearningState) -> dict[str, Any]:
    """GitHub 활동 데이터를 수집한다."""
    from collectors.github_collector import GitHubCollector

    collector = GitHubCollector()
    data = await collector.collect()
    logger.info("[Node] collect_github 완료 — repos=%d", len(data.get("repos", [])))
    return {"github_data": data}


async def collect_confluence(state: LearningState) -> dict[str, Any]:
    """Confluence 학습 이력을 수집한다."""
    from collectors.confluence_collector import ConfluenceCollector

    collector = ConfluenceCollector()
    history = await collector.collect()
    logger.info("[Node] collect_confluence 완료 — pages=%d", len(history))
    return {"confluence_history": history}


# ─── Tier 1: 프로파일 분석 ────────────────────────────────────────────────────

def analyze_profile(state: LearningState) -> dict[str, Any]:
    """사용자 기술 스택·숙련도 프로파일을 분석한다."""
    from agents.profile_analyzer import ProfileAnalyzer

    analyzer = ProfileAnalyzer()
    profile = analyzer.analyze(
        topic=state["topic"],
        github_data=state["github_data"] or {},
        confluence_history=state["confluence_history"] or [],
    )
    logger.info("[Node] analyze_profile 완료 — tech_stack=%s", profile.get("tech_stack"))
    return {"user_profile": profile}


# ─── Tier 2: 커리큘럼 설계 (Writer) ─────────────────────────────────────────

def design_curriculum(state: LearningState) -> dict[str, Any]:
    """단계별 학습 커리큘럼을 설계한다.

    재시도(retry) 시 State 의 validation_result 를 critic_feedback 으로 전달해
    Writer 가 Reviewer 피드백을 반영해 재작성하도록 한다.
    blind retry → feedback-driven targeted retry.
    """
    from agents.curriculum_designer import CurriculumDesigner

    # Reviewer(Critic) 피드백 추출 — 첫 호출이면 None
    critic_feedback: dict | None = None
    validation = state.get("validation_result")
    if validation and state.get("retry_count", 0) > 0:
        critic_feedback = validation
        logger.info(
            "[Node] design_curriculum 재작성 모드 — feedback issues=%s",
            validation.get("issues", []),
        )

    designer = CurriculumDesigner()
    curriculum = designer.design(
        topic=state["topic"],
        depth=state["depth"],
        user_profile=state["user_profile"] or {},
        critic_feedback=critic_feedback,          # ← 피드백 전달
    )
    logger.info(
        "[Node] design_curriculum 완료 — stages=%d retry=%d",
        len(curriculum.get("stages", [])),
        state.get("retry_count", 0),
    )
    return {"curriculum": curriculum}


# ─── Tier 2: 리소스 큐레이션 ─────────────────────────────────────────────────

def curate_resources(state: LearningState) -> dict[str, Any]:
    """커리큘럼 기반 학습 자료를 큐레이션한다."""
    from agents.resource_curator import ResourceCurator

    curator = ResourceCurator()
    resources = curator.curate(
        topic=state["topic"],
        curriculum=state["curriculum"] or {},
        user_profile=state["user_profile"] or {},
    )
    logger.info("[Node] curate_resources 완료 — resources=%d", len(resources))
    return {"resources": resources}


# ─── Tier 3: 검증 ────────────────────────────────────────────────────────────

def validate(state: LearningState) -> dict[str, Any]:
    """커리큘럼과 리소스의 품질을 검증한다 (Reviewer 역할).

    검증 결과를 validation_result(raw) 와
    review_score / review_feedback(명시적 State 필드) 에 동시에 기록한다.
    review_feedback 은 다음 retry 에서 Writer(CurriculumDesigner) 로 전달된다.
    """
    from agents.critic import Critic

    critic = Critic()
    result = critic.validate(
        topic=state["topic"],
        curriculum=state["curriculum"] or {},
        resources=state["resources"] or [],
        user_profile=state["user_profile"] or {},
    )

    score: float = result.get("score", 0.0)
    issues: list[str] = result.get("issues", [])
    corrections: list[str] = result.get("corrections", [])
    summary: str = result.get("summary", "")

    # Writer 루프백 시 전달할 피드백 요약
    feedback_lines = [summary] if summary else []
    for i, issue in enumerate(issues):
        fix = corrections[i] if i < len(corrections) else ""
        feedback_lines.append(f"- {issue}" + (f" → {fix}" if fix else ""))
    review_feedback = "\n".join(feedback_lines) if feedback_lines else None

    retry_count = state.get("retry_count", 0)
    logger.info(
        "[Node] validate(Reviewer) 완료 — passed=%s score=%.2f retry=%d",
        result.get("passed"), score, retry_count,
    )

    return {
        "validation_result": result,
        "review_score": score,               # State 명시적 필드
        "review_feedback": review_feedback,  # Writer 재호출 시 사용
    }


# ─── 출력 ────────────────────────────────────────────────────────────────────

def write_markdown(state: LearningState) -> dict[str, Any]:
    """검증된 커리큘럼을 마크다운 파일로 저장한다."""
    from outputs.markdown_writer import MarkdownWriter

    writer = MarkdownWriter()
    md = writer.write(
        topic=state["topic"],
        depth=state["depth"],
        curriculum=state["curriculum"] or {},
        resources=state["resources"] or [],
        validation_result=state["validation_result"] or {},
    )
    logger.info("[Node] write_markdown 완료")
    return {"final_markdown": md}


async def write_confluence(state: LearningState) -> dict[str, Any]:
    """Confluence 페이지를 생성한다."""
    from outputs.confluence_writer import ConfluenceWriter

    writer = ConfluenceWriter()
    page_id = await writer.create_page(
        topic=state["topic"],
        depth=state["depth"],
        curriculum=state["curriculum"] or {},
        resources=state["resources"] or [],
        validation_result=state["validation_result"] or {},
        markdown=state["final_markdown"] or "",
    )
    updates: dict[str, Any] = {}
    if page_id:
        updates["confluence_page_id"] = page_id
        logger.info("[Node] write_confluence 완료 — page_id=%s", page_id)
    else:
        errors = list(state.get("errors") or [])
        errors.append("Confluence 페이지 생성 실패 — 로컬 마크다운만 저장")
        updates["errors"] = errors
        logger.warning("[Node] write_confluence 실패 → graceful degradation")
    return updates


# ─── 재시도 핸들러 ────────────────────────────────────────────────────────────

def handle_retry(state: LearningState) -> dict[str, Any]:
    """검증 실패 시 재시도 카운터를 증가시킨다."""
    retry_count = state.get("retry_count", 0) + 1
    errors = list(state.get("errors") or [])
    issues = (state.get("validation_result") or {}).get("issues", [])
    errors.append(f"[retry #{retry_count}] 검증 실패: {issues}")
    logger.warning("[Node] handle_retry — retry_count=%d", retry_count)
    return {"retry_count": retry_count, "errors": errors}


def handle_max_retry(state: LearningState) -> dict[str, Any]:
    """최대 재시도 초과 시 에러를 기록하고 강제 종료한다."""
    errors = list(state.get("errors") or [])
    errors.append("최대 재시도 횟수 초과 — 파이프라인 강제 종료")
    logger.error("[Node] handle_max_retry — 파이프라인 종료")
    return {"errors": errors}


# ─── 라우팅 조건 ─────────────────────────────────────────────────────────────

def route_after_validation(state: LearningState) -> str:
    """검증 결과에 따라 다음 노드를 결정한다.

    Returns:
        "retry"        — 검증 실패 + retry_count < 2 → 커리큘럼 재설계
        "max_retry"    — retry_count >= 2            → 강제 종료
        "write"        — 검증 통과                   → 출력 단계
    """
    result = state.get("validation_result") or {}
    passed = result.get("passed", False)
    retry_count = state.get("retry_count", 0)

    if passed:
        return "write"
    if retry_count >= 2:
        return "max_retry"
    return "retry"
