from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.assessment import Assessment
from api.models.finding import Finding
from api.models.agent_log import AgentLog
from api.schemas.assessment import (
    CreateAssessmentRequest,
    RerunAssessmentRequest,
    AssessmentResponse,
    AssessmentListResponse,
)
from api.schemas.pagination import PaginationMeta
from api.services.lightweight_scanner import run_lightweight_scan
from api.services.robust_scanner import run_robust_scan
from api.utils.errors import VibeCheckError
from api.utils.pagination import paginate

router = APIRouter(tags=["Assessments"])


@router.post(
    "/v1/assessments",
    status_code=202,
    response_model=AssessmentResponse,
)
async def create_assessment(
    body: CreateAssessmentRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    from api.database import async_sessionmaker_factory

    if body.idempotency_key:
        q = select(Assessment).where(
            Assessment.idempotency_key == body.idempotency_key
        )
        result = await db.execute(q)
        existing = result.scalar_one_or_none()
        if existing:
            if existing.mode != body.mode:
                raise VibeCheckError.duplicate_idempotency_key()
            return AssessmentResponse.model_validate(existing)

    assessment = Assessment(
        mode=body.mode,
        status="queued",
        repo_url=body.repo_url,
        target_url=body.target_url,
        tunnel_session_id=body.tunnel_session_id,
        agents=body.agents,
        depth=body.depth,
        context_limit=body.context_limit,
        idempotency_key=body.idempotency_key,
    )
    db.add(assessment)
    await db.commit()
    await db.refresh(assessment)

    if body.mode == "lightweight":
        background_tasks.add_task(
            run_lightweight_scan,
            assessment_id=assessment.id,
            repo_url=body.repo_url,
            files=[f.model_dump() for f in body.files] if body.files else None,
            db_factory=async_sessionmaker_factory,
            context_limit=body.context_limit,
        )
    else:
        background_tasks.add_task(
            run_robust_scan,
            assessment_id=assessment.id,
            target_url=body.target_url,
            agent_names=body.agents,
            depth=body.depth,
            db_factory=async_sessionmaker_factory,
        )

    return AssessmentResponse.model_validate(assessment)


@router.get(
    "/v1/assessments",
    response_model=AssessmentListResponse,
)
async def list_assessments(
    db: AsyncSession = Depends(get_db),
    page: int = 1,
    per_page: int = 20,
    mode: str | None = None,
    status: str | None = None,
    sort: str = "-created_at",
):
    query = select(Assessment)
    if mode is not None:
        query = query.where(Assessment.mode == mode)
    if status is not None:
        query = query.where(Assessment.status == status)
    sort_column = sort.lstrip("-")
    order_col = getattr(Assessment, sort_column, Assessment.created_at)
    if sort.startswith("-"):
        query = query.order_by(order_col.desc())
    else:
        query = query.order_by(order_col.asc())

    items, meta = await paginate(db, query, page, per_page)
    return AssessmentListResponse(
        data=[AssessmentResponse.model_validate(a) for a in items],
        pagination=meta,
    )


@router.get(
    "/v1/assessments/{assessment_id}",
    response_model=AssessmentResponse,
)
async def get_assessment(
    assessment_id: str,
    db: AsyncSession = Depends(get_db),
):
    assessment = await db.get(Assessment, assessment_id)
    if not assessment:
        raise VibeCheckError.not_found("Assessment", assessment_id)
    return AssessmentResponse.model_validate(assessment)


@router.delete("/v1/assessments/{assessment_id}", status_code=204)
async def delete_assessment(
    assessment_id: str,
    db: AsyncSession = Depends(get_db),
):
    assessment = await db.get(Assessment, assessment_id)
    if not assessment:
        raise VibeCheckError.not_found("Assessment", assessment_id)
    await db.execute(delete(Finding).where(Finding.assessment_id == assessment_id))
    await db.execute(delete(AgentLog).where(AgentLog.assessment_id == assessment_id))
    await db.delete(assessment)
    await db.commit()


@router.post(
    "/v1/assessments/{assessment_id}/rerun",
    status_code=202,
    response_model=AssessmentResponse,
)
async def rerun_assessment(
    assessment_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    body: RerunAssessmentRequest | None = None,
):
    from api.database import async_sessionmaker_factory

    assessment = await db.get(Assessment, assessment_id)
    if not assessment:
        raise VibeCheckError.not_found("Assessment", assessment_id)
    if assessment.status not in ("complete", "failed"):
        raise VibeCheckError.assessment_in_progress()

    assessment.status = "queued"
    assessment.finding_counts = {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "info": 0,
        "total": 0,
    }
    assessment.completed_at = None
    if body:
        if body.agents is not None:
            assessment.agents = body.agents
        if body.idempotency_key is not None:
            assessment.idempotency_key = body.idempotency_key

    await db.execute(delete(Finding).where(Finding.assessment_id == assessment_id))
    await db.execute(delete(AgentLog).where(AgentLog.assessment_id == assessment_id))

    await db.commit()
    await db.refresh(assessment)

    if assessment.mode == "lightweight":
        background_tasks.add_task(
            run_lightweight_scan,
            assessment_id=assessment.id,
            repo_url=assessment.repo_url,
            files=None,
            db_factory=async_sessionmaker_factory,
            context_limit=assessment.context_limit,
        )
    else:
        background_tasks.add_task(
            run_robust_scan,
            assessment_id=assessment.id,
            target_url=assessment.target_url,
            agent_names=assessment.agents or ["recon", "auth", "injection", "config"],
            depth=assessment.depth,
            db_factory=async_sessionmaker_factory,
        )

    return AssessmentResponse.model_validate(assessment)
