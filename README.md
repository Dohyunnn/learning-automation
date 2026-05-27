# learning-automation

> AI 기반 개인 맞춤 학습 커리큘럼 자동 생성 시스템

GitHub 활동 + Confluence 학습 이력을 분석해 맞춤형 학습 커리큘럼을 생성하고,
Critic 에이전트가 검증한 뒤 Confluence 페이지로 자동 문서화하는 LangGraph 기반 멀티 에이전트 백엔드.

---

## 아키텍처

```
[입력]
  --topic "FastAPI"  --depth intermediate
         │
         ▼
┌─────────────────────────────────────────────────────┐
│               LangGraph Pipeline                    │
│                                                     │
│  ┌──────────────────┐  ┌──────────────────────┐    │
│  │  GitHub Collector│  │ Confluence Collector  │    │
│  │  (REST API v3)   │  │ (REST API v2)         │    │
│  └────────┬─────────┘  └──────────┬───────────┘    │
│           └──────────┬────────────┘                 │
│                      ▼                              │
│        ┌─────────────────────────┐                  │
│  Tier1 │   ProfileAnalyzer       │ claude-haiku-4-5 │
│        │  (분류·태깅·중복 감지)   │ <- 빠름, 저비용  │
│        └───────────┬─────────────┘                  │
│                    ▼                                │
│        ┌─────────────────────────┐                  │
│  Tier2 │   CurriculumDesigner    │ claude-sonnet-4-6│
│        │  (커리큘럼 생성)         │ + Prompt Cache  │
│        └───────────┬─────────────┘                  │
│                    ▼                                │
│        ┌─────────────────────────┐                  │
│  Tier2 │   ResourceCurator       │ claude-sonnet-4-6│
│        │  (자료 큐레이션)         │ + Prompt Cache  │
│        └───────────┬─────────────┘                  │
│                    ▼                                │
│        ┌─────────────────────────┐                  │
│  Tier3 │       Critic            │ claude-opus-4-7  │
│        │  (검증·교차확인)         │ <- 최고 정밀도   │
│        └───────────┬─────────────┘                  │
│                    │                                │
│          ┌─────────┴──────────┐                    │
│          │ route_after_valid  │                    │
│          └──┬──────┬──────────┘                    │
│        pass │  fail│  fail(retry>=2)               │
│             ▼      ▼          ▼                    │
│         write  handle_retry  handle_max_retry       │
│           │       │(->Tier2)       │(->END)         │
│           ▼                                        │
│  ┌─────────────────────────────────┐               │
│  │ MarkdownWriter -> ConfluenceWriter│              │
│  └─────────────────────────────────┘               │
└─────────────────────────────────────────────────────┘
         │
         ▼
[출력]
  output/{topic}_{depth}_{timestamp}.md
  Confluence 페이지 (설정 시 자동 생성)
```

### 3-tier 모델 라우팅 설계 의도

| Tier | 모델 | 역할 | 선택 이유 |
|------|------|------|-----------|
| Tier 1 | claude-haiku-4-5 | 분류·태깅 | 구조화된 분류 작업 → 속도↑ 비용↓ |
| Tier 2 | claude-sonnet-4-6 | 생성·설계 | 창의적 생성 + Prompt Caching으로 균형 |
| Tier 3 | claude-opus-4-7 | 검증·교차확인 | 할루시네이션 감지 최고 정밀도 필요 |

> 모든 작업에 고성능 모델을 사용하는 대신, 작업 특성에 따라 추론 수준을 분리해
> API 비용과 응답 속도를 동시에 최적화했습니다.

---

## 커밋 히스토리 (모델 진화)

```
Commit 1  feat: scaffold -- Sonnet 단일 모델 파이프라인
Commit 2  refactor: Critic -> Opus 4.7 (검증 품질 강화)
Commit 3  feat: Haiku 4.5 추가, 3-tier 비용 최적화 완성
Commit 4  docs: README + 아키텍처 다이어그램
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
├── graph/
│   ├── state.py                # LearningState TypedDict
│   ├── builder.py              # StateGraph 빌더
│   └── nodes.py                # 노드 함수
├── agents/
│   ├── profile_analyzer.py     # Tier 1: Haiku 분류·태깅
│   ├── curriculum_designer.py  # Tier 2: Sonnet 커리큘럼 생성
│   ├── resource_curator.py     # Tier 2: Sonnet 자료 큐레이션
│   └── critic.py               # Tier 3: Opus 검증
├── collectors/
│   ├── github_collector.py     # GitHub REST API (mock fallback)
│   └── confluence_collector.py # Confluence REST API v2
├── outputs/
│   ├── markdown_writer.py      # 마크다운 파일 저장
│   └── confluence_writer.py    # Confluence 페이지 생성
└── tests/
    └── test_pipeline.py        # 단위 16개 + 통합 1개
```

---

## 빠른 시작

### 1. 환경 설정

```bash
# uv 설치 (없는 경우)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 가상환경 + 의존성 설치
uv venv && uv pip install -e ".[dev]"

# 환경변수 설정
cp .env.example .env
# .env 파일에 ANTHROPIC_API_KEY 입력
```

### 2. CLI 실행

```bash
# FastAPI 학습 커리큘럼 생성 (intermediate)
python main.py --topic "FastAPI" --depth intermediate

# LangGraph 고급 커리큘럼 (Confluence 업로드 없이)
python main.py --topic "LangGraph" --depth advanced --no-confluence

# 초급 Python 커리큘럼
python main.py --topic "Python" --depth beginner --log-level DEBUG
```

### 3. FastAPI 서버 실행

```bash
uvicorn api:app --reload --port 8000
```

| 엔드포인트 | 설명 |
|-----------|------|
| `POST /generate` | `{"topic": "FastAPI", "depth": "intermediate"}` → `job_id` 반환 |
| `GET /jobs/{id}` | 작업 상태 조회 |
| `GET /health` | 헬스체크 |
| `GET /docs` | Swagger UI 자동 문서화 |

### 4. 테스트 실행

```bash
pytest tests/ -v
# 16 passed
```

---

## 환경변수

| 변수 | 필수 | 설명 |
|------|------|------|
| `ANTHROPIC_API_KEY` | ✅ | Anthropic API 키 |
| `GITHUB_TOKEN` | ❌ | 없으면 mock 데이터 사용 |
| `CONFLUENCE_BASE_URL` | ❌ | 없으면 로컬 마크다운만 저장 |
| `CONFLUENCE_EMAIL` | ❌ | Confluence 계정 이메일 |
| `CONFLUENCE_API_TOKEN` | ❌ | Confluence API 토큰 |
| `CONFLUENCE_SPACE_ID` | ❌ | 저장할 Confluence 스페이스 ID |
| `CONFLUENCE_PARENT_PAGE_ID` | ❌ | 부모 페이지 ID |

---

## 조건부 라우팅

```
validate 노드 결과
  passed == True                 -> write_markdown -> write_confluence -> END
  passed == False, retry < 2    -> handle_retry -> design_curriculum (재진입)
  passed == False, retry >= 2   -> handle_max_retry -> END (errors 기록)
```

Confluence 페이지 생성 실패 시 로컬 마크다운 파일은 항상 저장됩니다 (graceful degradation).

---

## 기술 스택

- **Python 3.11** · **uv** (의존성 관리)
- **LangGraph** (멀티 에이전트 오케스트레이션)
- **Anthropic Python SDK** (claude-haiku-4-5 / sonnet-4-6 / opus-4-7)
- **FastAPI** + **uvicorn** (REST API)
- **httpx** (Confluence REST API v2 호출)
- **pydantic-settings** (.env 로딩)
- **pytest** + **pytest-asyncio** (테스트)
