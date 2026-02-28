import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from api.database import create_tables
from api.routers import health, assessments, findings, logs, agents, tunnel
from api.utils.errors import VibeCheckError


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield


app = FastAPI(
    title="VibeCheck API",
    description="AI-powered security scanning for vibe-coded applications",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_id(request, call_next):
    request_id = str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(VibeCheckError)
async def vibecheck_error_handler(request, exc: VibeCheckError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "type": exc.type,
                "message": exc.message,
                "code": exc.code,
                "param": exc.param,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "type": "validation_error",
                "message": str(exc),
                "code": "VALIDATION_ERROR",
            }
        },
    )


app.include_router(health.router)
app.include_router(assessments.router)
app.include_router(findings.router)
app.include_router(logs.router)
app.include_router(agents.router)
app.include_router(tunnel.router)


