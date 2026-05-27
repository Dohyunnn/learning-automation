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
