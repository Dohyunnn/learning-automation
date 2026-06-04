"""파이프라인 단위 테스트 + 통합 테스트.

LLM 호출은 mock 처리하여 실제 API 비용 없이 검증한다.
"""
import json
from unittest.mock import MagicMock, patch

import pytest

# ─── fixtures ────────────────────────────────────────────────────────────────

MOCK_GITHUB_DATA = {
    "username": "test_user",
    "repos": [
        {
            "name": "fastapi-demo",
            "description": "FastAPI demo",
            "languages": {"Python": 8000},
            "stars": 5,
            "recent_commits": ["Add endpoint", "Fix bug"],
        }
    ],
    "top_languages": ["Python"],
    "total_repos": 1,
    "total_commits_last_month": 10,
}

MOCK_PROFILE = {
    "tech_stack": ["Python", "FastAPI"],
    "proficiency": {"Python": "intermediate", "FastAPI": "beginner"},
    "learning_history": [],
    "interests": ["FastAPI"],
    "gaps": ["testing", "deployment"],
}

MOCK_CURRICULUM = {
    "title": "FastAPI 학습 커리큘럼",
    "overview": "FastAPI 기반 REST API 개발 능력을 기른다.",
    "objectives": ["FastAPI 기초 이해", "REST API 구현"],
    "stages": [
        {
            "stage": 1,
            "title": "FastAPI 기초",
            "duration_hours": 8,
            "topics": ["라우팅", "Pydantic 모델"],
            "hands_on": "간단한 CRUD API 구현",
            "milestone": "GET/POST 엔드포인트 구현",
        }
    ],
    "total_duration_hours": 8,
    "prerequisites": ["Python 기초"],
}

MOCK_RESOURCES = [
    {
        "stage": 1,
        "title": "FastAPI 공식 문서",
        "type": "official_docs",
        "url": "https://fastapi.tiangolo.com",
        "description": "FastAPI 공식 튜토리얼",
        "estimated_hours": 3,
        "is_free": True,
    }
]

MOCK_VALIDATION_PASSED = {
    "passed": True,
    "score": 0.92,
    "issues": [],
    "corrections": [],
    "hallucination_risk": "low",
    "summary": "커리큘럼이 적절하게 구성되었습니다.",
}

MOCK_VALIDATION_FAILED = {
    "passed": False,
    "score": 0.45,
    "issues": ["학습 시간이 부족함"],
    "corrections": ["Stage 1 시간을 12시간으로 늘릴 것"],
    "hallucination_risk": "medium",
    "summary": "개선이 필요합니다.",
}


def _make_mock_response(content: dict | list) -> MagicMock:
    """anthropic.Anthropic.messages.create 응답을 흉내 낸 mock 객체."""
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=json.dumps(content, ensure_ascii=False))]
    mock_resp.usage = MagicMock(
        input_tokens=100,
        output_tokens=200,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    return mock_resp


# ─── Unit: ProfileAnalyzer ───────────────────────────────────────────────────

class TestProfileAnalyzer:
    def test_analyze_returns_profile(self):
        """mock LLM 응답으로 프로파일이 올바르게 파싱되는지 확인."""
        from agents.profile_analyzer import ProfileAnalyzer

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_mock_response(MOCK_PROFILE)

        analyzer = ProfileAnalyzer(client=mock_client)
        result = analyzer.analyze(
            topic="FastAPI",
            github_data=MOCK_GITHUB_DATA,
            confluence_history=[],
        )

        assert result["tech_stack"] == ["Python", "FastAPI"]
        assert "proficiency" in result
        mock_client.messages.create.assert_called_once()

    def test_analyze_fallback_on_api_error(self):
        """API 오류 시 fallback 프로파일을 반환하는지 확인."""
        import anthropic
        from agents.profile_analyzer import ProfileAnalyzer

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = anthropic.APIConnectionError(
            request=MagicMock()
        )

        analyzer = ProfileAnalyzer(client=mock_client)
        result = analyzer.analyze(
            topic="FastAPI",
            github_data=MOCK_GITHUB_DATA,
            confluence_history=[],
        )

        assert "tech_stack" in result
        assert "FastAPI" in result.get("interests", [])

    def test_profile_analyzer_uses_haiku_model(self):
        """v0.3: ProfileAnalyzer가 Haiku 4.5 모델을 사용하는지 확인."""
        from agents.profile_analyzer import MODEL, ProfileAnalyzer

        assert MODEL == "claude-haiku-4-5", (
            f"ProfileAnalyzer는 Haiku 4.5를 사용해야 합니다. 현재: {MODEL}"
        )
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_mock_response(MOCK_PROFILE)
        analyzer = ProfileAnalyzer(client=mock_client)
        assert analyzer.model == "claude-haiku-4-5"


# ─── Unit: 3-tier 모델 라우팅 검증 ───────────────────────────────────────────

class TestModelTierRouting:
    """3-tier 모델 분리 아키텍처 검증."""

    def test_tier1_uses_haiku(self):
        """Tier 1 (분류·태깅) — Haiku 4.5 사용."""
        from agents.profile_analyzer import MODEL as ANALYZER_MODEL
        assert ANALYZER_MODEL == "claude-haiku-4-5"

    def test_tier2_uses_sonnet(self):
        """Tier 2 (생성·설계) — Sonnet 4.6 사용."""
        from agents.curriculum_designer import MODEL as DESIGNER_MODEL
        from agents.resource_curator import MODEL as CURATOR_MODEL
        assert DESIGNER_MODEL == "claude-sonnet-4-6"
        assert CURATOR_MODEL == "claude-sonnet-4-6"

    def test_tier3_uses_opus(self):
        """Tier 3 (검증) — Opus 4.7 사용."""
        from agents.critic import MODEL as CRITIC_MODEL
        assert CRITIC_MODEL == "claude-opus-4-7"

    def test_all_tiers_distinct(self):
        """세 Tier가 모두 다른 모델을 사용하는지 확인."""
        from agents.critic import MODEL as CRITIC_MODEL
        from agents.curriculum_designer import MODEL as DESIGNER_MODEL
        from agents.profile_analyzer import MODEL as ANALYZER_MODEL
        models = {ANALYZER_MODEL, DESIGNER_MODEL, CRITIC_MODEL}
        assert len(models) == 3, "3-tier는 서로 다른 모델을 사용해야 합니다."


# ─── Unit: CurriculumDesigner ────────────────────────────────────────────────

class TestCurriculumDesigner:
    def test_design_returns_curriculum(self):
        """mock LLM 응답으로 커리큘럼이 올바르게 파싱되는지 확인."""
        from agents.curriculum_designer import CurriculumDesigner

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_mock_response(MOCK_CURRICULUM)

        designer = CurriculumDesigner(client=mock_client)
        result = designer.design(
            topic="FastAPI",
            depth="intermediate",
            user_profile=MOCK_PROFILE,
        )

        assert result["title"] == "FastAPI 학습 커리큘럼"
        assert len(result["stages"]) == 1
        assert result["total_duration_hours"] == 8

    def test_design_uses_cache_control(self):
        """prompt caching 파라미터가 전달되는지 확인."""
        from agents.curriculum_designer import CurriculumDesigner

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_mock_response(MOCK_CURRICULUM)

        designer = CurriculumDesigner(client=mock_client)
        designer.design(
            topic="FastAPI",
            depth="beginner",
            user_profile=MOCK_PROFILE,
        )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        system = call_kwargs.get("system", [])
        # 시스템 프롬프트에 cache_control 이 있어야 함
        assert any(
            block.get("cache_control") == {"type": "ephemeral"}
            for block in system
            if isinstance(block, dict)
        )


# ─── Unit: Critic ────────────────────────────────────────────────────────────

class TestCritic:
    def test_validate_passed(self):
        """통과 응답을 올바르게 파싱하는지 확인."""
        from agents.critic import Critic

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_mock_response(
            MOCK_VALIDATION_PASSED
        )

        critic = Critic(client=mock_client)
        result = critic.validate(
            topic="FastAPI",
            curriculum=MOCK_CURRICULUM,
            resources=MOCK_RESOURCES,
            user_profile=MOCK_PROFILE,
        )

        assert result["passed"] is True
        assert result["score"] == 0.92
        assert result["hallucination_risk"] == "low"

    def test_validate_failed_returns_issues(self):
        """실패 응답에서 issues 목록이 반환되는지 확인."""
        from agents.critic import Critic

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_mock_response(
            MOCK_VALIDATION_FAILED
        )

        critic = Critic(client=mock_client)
        result = critic.validate(
            topic="FastAPI",
            curriculum=MOCK_CURRICULUM,
            resources=MOCK_RESOURCES,
            user_profile=MOCK_PROFILE,
        )

        assert result["passed"] is False
        assert len(result["issues"]) > 0

    def test_critic_uses_opus_model(self):
        """v0.2: Critic이 Opus 4.7 모델을 사용하는지 확인."""
        from agents.critic import MODEL, Critic

        assert MODEL == "claude-opus-4-7", (
            f"Critic은 Opus 4.7을 사용해야 합니다. 현재: {MODEL}"
        )
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_mock_response(
            MOCK_VALIDATION_PASSED
        )
        critic = Critic(client=mock_client)
        assert critic.model == "claude-opus-4-7"


# ─── Unit: Routing Logic ─────────────────────────────────────────────────────

class TestRouting:
    def test_route_write_on_passed(self):
        """검증 통과 시 'write' 라우팅 반환."""
        from graph.nodes import route_after_validation

        state = {
            "topic": "FastAPI",
            "depth": "intermediate",
            "validation_result": MOCK_VALIDATION_PASSED,
            "retry_count": 0,
            "errors": [],
        }
        assert route_after_validation(state) == "write"

    def test_route_retry_on_first_failure(self):
        """첫 번째 실패 시 'retry' 라우팅."""
        from graph.nodes import route_after_validation

        state = {
            "topic": "FastAPI",
            "depth": "intermediate",
            "validation_result": MOCK_VALIDATION_FAILED,
            "retry_count": 0,
            "errors": [],
        }
        assert route_after_validation(state) == "retry"

    def test_route_max_retry_on_overflow(self):
        """retry_count >= 2 시 'max_retry' 라우팅."""
        from graph.nodes import route_after_validation

        state = {
            "topic": "FastAPI",
            "depth": "intermediate",
            "validation_result": MOCK_VALIDATION_FAILED,
            "retry_count": 2,
            "errors": [],
        }
        assert route_after_validation(state) == "max_retry"


# ─── Integration: 전체 파이프라인 (mock GitHub + mock LLM) ───────────────────

class TestIntegrationPipeline:
    @pytest.mark.asyncio
    async def test_full_pipeline_produces_markdown(self):
        """
        mock GitHub 데이터 → 전체 파이프라인 → markdown 출력 확인.
        LLM 호출은 모두 mock 처리.
        """
        from graph.builder import compile_graph

        # 각 에이전트의 LLM 응답을 mock
        profile_resp = _make_mock_response(MOCK_PROFILE)
        curriculum_resp = _make_mock_response(MOCK_CURRICULUM)
        resources_resp = _make_mock_response({"resources": MOCK_RESOURCES})
        critic_resp = _make_mock_response(MOCK_VALIDATION_PASSED)

        with (
            patch(
                "agents.profile_analyzer.ProfileAnalyzer.analyze",
                return_value=MOCK_PROFILE,
            ),
            patch(
                "agents.curriculum_designer.CurriculumDesigner.design",
                return_value=MOCK_CURRICULUM,
            ),
            patch(
                "agents.resource_curator.ResourceCurator.curate",
                return_value=MOCK_RESOURCES,
            ),
            patch(
                "agents.critic.Critic.validate",
                return_value=MOCK_VALIDATION_PASSED,
            ),
            patch(
                "collectors.github_collector.GitHubCollector.collect",
                return_value=MOCK_GITHUB_DATA,
            ),
            patch(
                "collectors.confluence_collector.ConfluenceCollector.collect",
                return_value=[],
            ),
            patch(
                "outputs.confluence_writer.ConfluenceWriter.create_page",
                return_value=None,  # Confluence 미설정 → graceful degradation
            ),
        ):
            graph = compile_graph()
            initial_state = {
                "topic": "FastAPI",
                "depth": "intermediate",
                "github_data": None,
                "confluence_history": None,
                "user_profile": None,
                "curriculum": None,
                "resources": None,
                "validation_result": None,
                "review_score": None,
                "review_feedback": None,
                "retry_count": 0,
                "final_markdown": None,
                "confluence_page_id": None,
                "errors": [],
            }
            result = await graph.ainvoke(initial_state)

        # 마크다운이 생성되었는지 확인
        assert result.get("final_markdown") is not None
        assert "FastAPI" in result["final_markdown"]
        assert result.get("curriculum") == MOCK_CURRICULUM
        # Confluence 실패 → errors에 기록
        assert isinstance(result.get("errors"), list)


# ─── Unit: 도구 실행 함수 (tools.py) ─────────────────────────────────────────

class TestToolExecutors:
    """tools.py 로컬 실행 함수 단위 테스트."""

    def test_classify_tech_stack_python_backend(self):
        """Python 중심 레포 → backend 분류."""
        from agents.tools import execute_classify_tech_stack

        result = json.loads(execute_classify_tech_stack({
            "languages": {"Python": 8000, "Dockerfile": 200},
            "keywords": ["FastAPI", "REST API"],
            "topic": "FastAPI",
        }))

        assert "Python" in result["top_languages"]
        assert result["stack_type"] == "backend"
        assert result["topic_familiarity"] == "experienced"

    def test_estimate_duration_advanced_no_prior(self):
        """advanced + 사전 지식 없음 → 30시간."""
        from agents.tools import execute_estimate_duration

        result = json.loads(execute_estimate_duration({
            "topic": "LangGraph",
            "depth": "advanced",
            "stage_count": 3,
            "has_prior_knowledge": False,
        }))

        assert result["total_hours"] == 30
        assert result["hours_per_stage"] == 10.0

    def test_estimate_duration_with_prior_knowledge(self):
        """사전 지식 있으면 30% 시간 단축."""
        from agents.tools import execute_estimate_duration

        result = json.loads(execute_estimate_duration({
            "topic": "LangGraph",
            "depth": "advanced",
            "stage_count": 3,
            "has_prior_knowledge": True,
        }))

        assert result["total_hours"] == 21  # 30 * 0.7

    def test_score_curriculum_passes_good_curriculum(self):
        """모든 항목 충족 커리큘럼 → 0.75 이상."""
        from agents.tools import execute_score_curriculum

        result = json.loads(execute_score_curriculum({
            "has_clear_objectives": True,
            "stage_count": 3,
            "total_hours": 20,
            "hours_realistic": True,
            "depth_match": True,
            "has_hands_on": True,
            "issues_found": [],
            "hallucination_risk": "low",
        }))

        assert result["passed"] is True
        assert result["score"] >= 0.75

    def test_score_curriculum_fails_bad_curriculum(self):
        """문제 다수 + hallucination high → 0.75 미만."""
        from agents.tools import execute_score_curriculum

        result = json.loads(execute_score_curriculum({
            "has_clear_objectives": False,
            "stage_count": 1,
            "total_hours": 200,
            "hours_realistic": False,
            "depth_match": False,
            "has_hands_on": False,
            "issues_found": ["시간 비현실적", "목표 불명확", "수준 부적합"],
            "hallucination_risk": "high",
        }))

        assert result["passed"] is False
        assert result["score"] < 0.75

    def test_dispatch_tool_routes_correctly(self):
        """dispatch_tool 이 올바른 실행 함수를 호출하는지 확인."""
        from agents.tools import dispatch_tool

        result = json.loads(dispatch_tool("classify_tech_stack", {
            "languages": {"Python": 5000},
            "keywords": [],
            "topic": "Python",
        }))
        assert "top_languages" in result

        result2 = json.loads(dispatch_tool("unknown_tool", {}))
        assert "error" in result2


# ─── Unit: tool_use 패턴 ─────────────────────────────────────────────────────

class TestToolUsePattern:
    """tool_use 멀티턴 패턴 검증."""

    def _make_tool_use_response(self, tool_name: str, tool_input: dict) -> MagicMock:
        """stop_reason=tool_use 인 mock 응답."""
        mock_resp = MagicMock()
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = tool_name
        tool_block.input = tool_input
        tool_block.id = "tool_123"
        mock_resp.content = [tool_block]
        mock_resp.stop_reason = "tool_use"
        mock_resp.usage = MagicMock(
            input_tokens=100, output_tokens=50,
            cache_read_input_tokens=0, cache_creation_input_tokens=0,
        )
        return mock_resp

    def test_profile_analyzer_handles_tool_use_flow(self):
        """ProfileAnalyzer 가 tool_use → tool_result → final 2-turn 흐름을 처리."""
        from agents.profile_analyzer import ProfileAnalyzer

        tool_resp = self._make_tool_use_response(
            "classify_tech_stack",
            {"languages": {"Python": 8000}, "keywords": ["FastAPI"], "topic": "FastAPI"},
        )
        final_resp = _make_mock_response(MOCK_PROFILE)

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [tool_resp, final_resp]

        analyzer = ProfileAnalyzer(client=mock_client)
        result = analyzer.analyze("FastAPI", MOCK_GITHUB_DATA, [])

        # 2번 호출: 1차(도구 요청) + 2차(결과 반영)
        assert mock_client.messages.create.call_count == 2
        assert "tech_stack" in result

    def test_curriculum_designer_passes_feedback_on_retry(self):
        """재시도 시 critic_feedback 가 메시지에 포함되는지 확인."""
        from agents.curriculum_designer import CurriculumDesigner

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_mock_response(MOCK_CURRICULUM)

        designer = CurriculumDesigner(client=mock_client)
        designer.design(
            topic="FastAPI",
            depth="intermediate",
            user_profile=MOCK_PROFILE,
            critic_feedback=MOCK_VALIDATION_FAILED,  # 재시도 피드백
        )

        # 시스템 프롬프트에 RETRY_ADDENDUM 이 포함되어야 함
        call_kwargs = mock_client.messages.create.call_args.kwargs
        system = call_kwargs.get("system", [])
        system_text = "".join(
            b.get("text", "") for b in system if isinstance(b, dict)
        )
        assert "재작성 모드" in system_text


# ─── Unit: Reviewer → Writer 피드백 루프 ─────────────────────────────────────

class TestReviewerWriterLoop:
    """Reviewer 실패 → Writer 피드백 루프 검증."""

    def test_validate_node_writes_review_score_to_state(self):
        """validate 노드가 review_score 와 review_feedback 을 State 에 기록."""
        from graph.nodes import validate

        with patch("agents.critic.Critic.validate", return_value=MOCK_VALIDATION_FAILED):
            state = {
                "topic": "FastAPI", "depth": "intermediate",
                "curriculum": MOCK_CURRICULUM, "resources": MOCK_RESOURCES,
                "user_profile": MOCK_PROFILE, "retry_count": 0,
            }
            updates = validate(state)

        assert updates["review_score"] == MOCK_VALIDATION_FAILED["score"]
        assert updates["review_feedback"] is not None
        assert "학습 시간이 부족함" in updates["review_feedback"]

    def test_design_curriculum_passes_feedback_on_retry(self):
        """retry_count > 0 이면 design_curriculum 이 critic_feedback 를 전달."""
        from graph.nodes import design_curriculum

        received_feedback = {}

        def capture_design(topic, depth, user_profile, critic_feedback=None):
            received_feedback["feedback"] = critic_feedback
            return MOCK_CURRICULUM

        with patch("agents.curriculum_designer.CurriculumDesigner.design",
                   side_effect=capture_design):
            state = {
                "topic": "FastAPI", "depth": "intermediate",
                "user_profile": MOCK_PROFILE,
                "validation_result": MOCK_VALIDATION_FAILED,
                "retry_count": 1,  # 재시도 상황
            }
            design_curriculum(state)

        # 피드백이 전달되었는지 확인
        assert received_feedback["feedback"] is not None
        assert received_feedback["feedback"]["passed"] is False

    def test_design_curriculum_no_feedback_on_first_call(self):
        """첫 호출(retry_count=0)에서는 critic_feedback=None 이어야 함."""
        from graph.nodes import design_curriculum

        received_feedback = {}

        def capture_design(topic, depth, user_profile, critic_feedback=None):
            received_feedback["feedback"] = critic_feedback
            return MOCK_CURRICULUM

        with patch("agents.curriculum_designer.CurriculumDesigner.design",
                   side_effect=capture_design):
            state = {
                "topic": "FastAPI", "depth": "intermediate",
                "user_profile": MOCK_PROFILE,
                "validation_result": None,
                "retry_count": 0,  # 첫 호출
            }
            design_curriculum(state)

        assert received_feedback["feedback"] is None
