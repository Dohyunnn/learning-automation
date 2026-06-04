# learning-automation

> AI 기반 개인 맞춤 학습 커리큘럼 자동 생성 시스템

GitHub 활동 + Confluence 학습 이력을 분석해 맞춤형 학습 커리큘럼을 생성하고,
Critic 에이전트가 검증한 뒤 Confluence 페이지로 자동 문서화하는
**LangGraph 기반 멀티 에이전트 백엔드**.

---

## 전체 파이프라인 흐름

```
python main.py --topic "FastAPI" --depth intermediate
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│                    LangGraph StateGraph                        │
│                                                                │
│  ┌─────────────────┐     ┌──────────────────────┐             │
│  │  GitHub Collector│     │ Confluence Collector  │ (병렬 실행) │
│  │  토큰 없으면      │     │ 미설정 시 빈 리스트   │             │
│  │  mock 데이터     │     │ 반환                  │             │
│  └────────┬────────┘     └──────────┬────────────┘             │
│           └─────────────┬───────────┘                          │
│                         ▼                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Tier 1  ProfileAnalyzer         claude-haiku-4-5        │  │
│  │          도구: classify_tech_stack                        │  │
│  │          ① Haiku 가 도구 호출 파라미터 결정               │  │
│  │          ② 로컬에서 언어 비중으로 숙련도 계산             │  │
│  │          ③ 결과 반환 → 최종 프로파일 JSON 생성            │  │
│  └──────────────────────────┬───────────────────────────────┘  │
│                             ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Tier 2  CurriculumDesigner      claude-sonnet-4-6       │  │
│  │  (Writer) 도구: estimate_duration                         │  │
│  │           도구: apply_critic_feedback  (재시도 시만 호출)  │  │
│  │           + Prompt Caching 적용                           │  │
│  └──────────────────────────┬───────────────────────────────┘  │
│                             ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Tier 2  ResourceCurator         claude-sonnet-4-6       │  │
│  │          + Prompt Caching 적용                           │  │
│  └──────────────────────────┬───────────────────────────────┘  │
│                             ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Tier 3  Critic (Reviewer)       claude-opus-4-7         │  │
│  │          도구: score_curriculum                           │  │
│  │          ① Opus 가 커리큘럼 분석 후 항목별 점수 파라미터 결정│  │
│  │          ② 도구가 가중치 채점 → 0.0~1.0 점수 반환         │  │
│  │          ③ passed / issues / corrections 최종 판정       │  │
│  └──────────────────────────┬───────────────────────────────┘  │
│                             │                                  │
│              ┌──────────────▼──────────────┐                   │
│              │     route_after_validation   │                  │
│              └──────┬──────────────┬────────┘                  │
│                     │              │                           │
│          score≥0.75 │     score<0.75 AND retry<2              │
│                     │              │                           │
│                     │         ┌────▼──────┐                   │
│                     │         │handle_retry│                   │
│                     │         │retry_count+1                  │
│                     │         │review_feedback                │
│                     │         │  State에 보존                 │
│                     │         └────┬──────┘                   │
│                     │              │                           │
│                     │    ┌─────────▼──────────────────────┐   │
│                     │    │  CurriculumDesigner (재호출)     │   │
│                     │    │  이번엔 critic_feedback 포함!   │   │
│                     │    │  "이런 문제 있었으니 고쳐서 써" │   │
│                     │    └─────────────────────────────────┘   │
│                     │                                         │
│              retry≥2 ──→ handle_max_retry ──→ errors 기록 → END│
│                     │                                         │
│                     ▼                                         │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  MarkdownWriter ──→ ConfluenceWriter                     │  │
│  │  output/*.md 저장    페이지 자동 생성                      │  │
│  │                      실패해도 md는 항상 저장 (graceful)   │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

---

## 3-tier 모델 라우팅

| Tier | 모델 | 에이전트 | 역할 | 선택 이유 |
|------|------|----------|------|-----------|
| Tier 1 | claude-haiku-4-5 | ProfileAnalyzer | 분류·태깅 | 구조화된 분류 → 속도↑ 비용↓ |
| Tier 2 | claude-sonnet-4-6 | CurriculumDesigner, ResourceCurator | 생성·설계 | 창의적 생성 + Prompt Caching |
| Tier 3 | claude-opus-4-7 | Critic (Reviewer) | 검증·교차확인 | 할루시네이션 감지 최고 정밀도 |

> 모든 작업에 고성능 모델을 사용하는 대신, 작업 특성에 따라 추론 수준을 분리해
> **API 비용과 응답 속도를 동시에 최적화**했습니다.

---

## 에이전트별 독립 도구 (tool_use)

각 에이전트는 자신의 역할에 맞는 도구만 보유합니다.
LLM이 도구 호출을 결정하고, 로컬 함수가 실행한 결과를 다시 LLM에 전달합니다.

```
에이전트                도구                     로컬 실행 로직
─────────────────────────────────────────────────────────────────
ProfileAnalyzer    classify_tech_stack    언어 바이트 비중 →
(Haiku)                                  숙련도(beginner/
                                         intermediate/advanced)
                                         스택 유형(backend/
                                         frontend/fullstack)

CurriculumDesigner estimate_duration     depth × 사전지식 여부
(Sonnet / Writer)                        → 현실적 학습 시간 추정

                   apply_critic_feedback issues + corrections
                   (재시도 시만 호출)    → 개선 계획 구조화

Critic             score_curriculum      항목별 가중치 채점:
(Opus / Reviewer)                        목표 명확(0.20)
                                         수준 적합(0.20)
                                         시간 현실(0.15)
                                         실습 포함(0.15)
                                         단계 수  (0.15)
                                         hallucin.(0.15)
                                         → 0.0~1.0 점수
                                         → 0.75 이상 통과
```

---

## Reviewer ↔ Writer 피드백 루프

```
          LangGraph State
          ┌────────────────────────────────┐
          │ review_score:    0.45          │  ← Critic 이 기록
          │ review_feedback: "시간 부족,   │  ← Critic 이 기록
          │                  URL 불명확"   │
          │ retry_count:     1             │  ← 루프 카운터
          └────────────────────────────────┘
                 ↑ 읽기               ↑ 쓰기
                 │                    │
      ┌──────────┴────┐    ┌──────────┴──────────┐
      │  Writer        │    │  Reviewer (Critic)   │
      │ (Curriculum    │    │                      │
      │  Designer)     │    │  score_curriculum    │
      │                │    │  도구로 채점           │
      │  피드백 있으면  │    │  → issues/corrections│
      │  재작성 모드   │    │  → State 에 기록      │
      └───────────────┘    └──────────────────────┘
              ↑                        │
              │      passed = False    │
              └────────────────────────┘
                   루프백 (최대 2회)
                   3회째 → 강제 종료 + errors 기록
```

---

## 커밋 히스토리 (설계 진화)

```
65b3ca4  feat: scaffold — Sonnet 단일 모델 파이프라인
a456178  refactor: Critic → Opus 4.7 (검증 품질 강화)
eb0cc06  feat: Haiku 4.5 추가, 3-tier 비용 최적화
7a126a9  docs: README + 아키텍처 다이어그램 초안
3618daf  feat: 에이전트별 독립 도구 정의 + State 필드 추가
dd4f0d5  feat(profile-analyzer): tool_use — classify_tech_stack
ac8d329  feat(curriculum-designer): tool_use + Writer 피드백 루프
6b49085  feat(critic): tool_use — score_curriculum 구조화 채점
d3cf81e  fix(nodes): Reviewer 피드백 → Writer 루프 연결
a39fd36  test: tool_use + 피드백 루프 테스트 (27개 전부 통과)
```

---

## 프로젝트 구조

```
learning-automation/
├── pyproject.toml              # uv 의존성 관리
├── .env.example                # 환경변수 템플릿
├── config.yaml                 # 모델·파이프라인 설정
├── main.py                     # CLI 진입점 (Typer)
├── api.py                      # FastAPI REST 엔드포인트
│
├── graph/
│   ├── state.py                # LearningState TypedDict
│   │                           # (review_score, review_feedback,
│   │                           #  retry_count 으로 루프 제어)
│   ├── builder.py              # StateGraph 노드·엣지 연결
│   └── nodes.py                # 노드 함수 + 라우팅 조건
│
├── agents/
│   ├── tools.py                # 에이전트별 도구 정의 + 로컬 실행 함수
│   ├── profile_analyzer.py     # Tier 1: Haiku — 분류·태깅
│   ├── curriculum_designer.py  # Tier 2: Sonnet — 생성 (Writer)
│   ├── resource_curator.py     # Tier 2: Sonnet — 자료 큐레이션
│   └── critic.py               # Tier 3: Opus — 검증 (Reviewer)
│
├── collectors/
│   ├── github_collector.py     # GitHub REST API v3 (mock fallback)
│   └── confluence_collector.py # Confluence REST API v2
│
├── outputs/
│   ├── markdown_writer.py      # output/*.md 저장
│   └── confluence_writer.py    # Confluence 페이지 생성 (graceful)
│
└── tests/
    └── test_pipeline.py        # 27개 테스트 (단위 26 + 통합 1)
                                # TestToolExecutors     (6)
                                # TestToolUsePattern    (2)
                                # TestReviewerWriterLoop(3)
                                # TestModelTierRouting  (4)
                                # TestProfileAnalyzer   (3)
                                # TestCurriculumDesigner(2)
                                # TestCritic            (3)
                                # TestRouting           (3)
                                # TestIntegrationPipeline(1)
```

---

## 빠른 시작

### 1. 환경 설정

```bash
# uv 설치
curl -LsSf https://astral.sh/uv/install.sh | sh

# 가상환경 + 의존성 설치
uv venv && uv pip install -e ".[dev]"

# 환경변수 설정
cp .env.example .env
# .env 에 ANTHROPIC_API_KEY 필수 입력
```

### 2. CLI 실행

```bash
# FastAPI 커리큘럼 생성 (Confluence 포함)
python main.py --topic "FastAPI" --depth intermediate

# Confluence 없이 로컬 마크다운만 저장
python main.py --topic "LangGraph" --depth advanced --no-confluence

# 초급 커리큘럼 + 디버그 로그
python main.py --topic "Python" --depth beginner --log-level DEBUG
```

### 3. FastAPI 서버 실행

```bash
uvicorn api:app --reload --port 8000
```

| 엔드포인트 | 설명 |
|-----------|------|
| `POST /generate` | `{"topic": "FastAPI", "depth": "intermediate"}` → `job_id` 반환 |
| `GET /jobs/{id}` | 작업 상태 조회 (pending / running / completed / failed) |
| `GET /health` | 헬스체크 |
| `GET /docs` | Swagger UI 자동 문서화 |

### 4. 테스트 실행

```bash
pytest tests/ -v
# 27 passed
```

---

## 환경변수

| 변수 | 필수 | 설명 |
|------|------|------|
| `ANTHROPIC_API_KEY` | ✅ | Anthropic API 키 |
| `GITHUB_TOKEN` | ❌ | 없으면 mock 데이터로 대체 |
| `CONFLUENCE_BASE_URL` | ❌ | 없으면 로컬 마크다운만 저장 |
| `CONFLUENCE_EMAIL` | ❌ | Confluence 계정 이메일 |
| `CONFLUENCE_API_TOKEN` | ❌ | Confluence API 토큰 |
| `CONFLUENCE_SPACE_ID` | ❌ | 저장할 스페이스 ID |
| `CONFLUENCE_PARENT_PAGE_ID` | ❌ | 부모 페이지 ID |

---

## 조건부 라우팅 규칙

```
validate 노드 (Critic / Reviewer) 판정 결과
  score >= 0.75                  → write_markdown → write_confluence → END
  score <  0.75, retry_count < 2 → handle_retry
                                   → design_curriculum (critic_feedback 전달)
                                   → [Writer 재작성 루프]
  score <  0.75, retry_count >= 2 → handle_max_retry → errors 기록 → END
```

Confluence 페이지 생성 실패 시 로컬 마크다운 파일은 항상 저장됩니다 (graceful degradation).

---

## 기술 스택

- **Python 3.11** · **uv** (의존성 관리)
- **LangGraph** (멀티 에이전트 오케스트레이션 · StateGraph)
- **Anthropic Python SDK** (claude-haiku-4-5 / sonnet-4-6 / opus-4-7 · tool_use · prompt caching)
- **FastAPI** + **uvicorn** (REST API · Swagger 자동 문서화)
- **httpx** (Confluence REST API v2 · GitHub REST API v3)
- **pydantic-settings** (.env 로딩)
- **pytest** + **pytest-asyncio** (27개 테스트)
