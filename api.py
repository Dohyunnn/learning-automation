"""FastAPI REST 엔드포인트.

엔드포인트:
    POST /generate      : 학습 커리큘럼 생성 작업 시작 → job_id 반환
    GET  /jobs/{job_id} : 작업 상태 조회
    GET  /health        : 헬스체크
"""
import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Learning Automation API",
    description="AI 기반 개인 맞춤 학습 커리큘럼 자동 생성 시스템",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# 인메모리 작업 저장소 (프로덕션에서는 Redis 등으로 교체)
_jobs: dict[str, dict[str, Any]] = {}


# ─── 요청/응답 모델 ──────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    topic: str
    depth: Literal["beginner", "intermediate", "advanced"] = "intermediate"

    @field_validator("topic")
    @classmethod
    def topic_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("topic은 비어 있을 수 없습니다.")
        return v.strip()


class GenerateResponse(BaseModel):
    job_id: str
    status: str
    message: str


class JobStatus(BaseModel):
    job_id: str
    status: Literal["pending", "running", "completed", "failed"]
    topic: str
    depth: str
    created_at: str
    completed_at: str | None = None
    result_summary: dict | None = None
    errors: list[str] = []


# ─── 백그라운드 작업 ─────────────────────────────────────────────────────────

async def _run_pipeline(job_id: str, topic: str, depth: str) -> None:
    """백그라운드에서 LangGraph 파이프라인을 실행한다."""
    from graph.builder import compile_graph

    _jobs[job_id]["status"] = "running"
    logger.info("[API] job=%s 시작 topic=%s depth=%s", job_id, topic, depth)

    try:
        graph = compile_graph()
        initial_state = {
            "topic": topic,
            "depth": depth,
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

        validation = result.get("validation_result") or {}
        _jobs[job_id].update(
            {
                "status": "completed",
                "completed_at": datetime.utcnow().isoformat(),
                "result_summary": {
                    "passed": validation.get("passed"),
                    "score": validation.get("score"),
                    "hallucination_risk": validation.get("hallucination_risk"),
                    "retry_count": result.get("retry_count", 0),
                    "confluence_page_id": result.get("confluence_page_id"),
                    "has_markdown": bool(result.get("final_markdown")),
                },
                "errors": result.get("errors") or [],
            }
        )
        logger.info("[API] job=%s 완료", job_id)
    except Exception as e:
        logger.exception("[API] job=%s 실패: %s", job_id, e)
        _jobs[job_id].update(
            {
                "status": "failed",
                "completed_at": datetime.utcnow().isoformat(),
                "errors": [str(e)],
            }
        )


# ─── 엔드포인트 ──────────────────────────────────────────────────────────────

@app.post("/generate", response_model=GenerateResponse, status_code=202)
async def generate(
    req: GenerateRequest, background_tasks: BackgroundTasks
) -> GenerateResponse:
    """학습 커리큘럼 생성 작업을 시작한다. job_id를 즉시 반환한다."""
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "topic": req.topic,
        "depth": req.depth,
        "created_at": datetime.utcnow().isoformat(),
        "completed_at": None,
        "result_summary": None,
        "errors": [],
    }
    background_tasks.add_task(_run_pipeline, job_id, req.topic, req.depth)
    logger.info("[API] job=%s 등록 topic=%s", job_id, req.topic)
    return GenerateResponse(
        job_id=job_id,
        status="pending",
        message=f"작업이 시작되었습니다. GET /jobs/{job_id} 로 상태를 확인하세요.",
    )


@app.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job(job_id: str) -> JobStatus:
    """작업 상태를 조회한다."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"job_id '{job_id}' 를 찾을 수 없습니다.")
    return JobStatus(**job)


@app.get("/health")
async def health() -> dict[str, str]:
    """헬스체크 엔드포인트."""
    return {"status": "ok", "version": "0.1.0"}
