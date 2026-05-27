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


# ─── Tier 2: 커리큘럼 설계 ───────────────────────────────────────────────────

def design_curriculum(state: LearningState) -> dict[str, Any]:
    """단계별 학습 커리큘럼을 설계한다."""
    from agents.curriculum_designer import CurriculumDesigner

    designer = CurriculumDesigner()
    curriculum = designer.design(
        topic=state["topic"],
        depth=state["depth"],
        user_profile=state["user_profile"] or {},
    )
    logger.info(
        "[Node] design_curriculum 완료 — stages=%d",
        len(curriculum.get("stages", [])),
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
    """커리큘럼과 리소스의 품질을 검증한다."""
    from agents.critic import Critic

    critic = Critic()
    result = critic.validate(
        topic=state["topic"],
        curriculum=state["curriculum"] or {},
        resources=state["resources"] or [],
        user_profile=state["user_profile"] or {},
    )
    retry_count = state.get("retry_count", 0)
    logger.info(
        "[Node] validate 완료 — passed=%s score=%.2f retry=%d",
        result.get("passed"),
        result.get("score", 0.0),
        retry_count,
    )
    return {"validation_result": result}


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
