"""HTTP composition root. Domain logic lives in features; no jobs run at import time."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app import graph
from app.features.auth.router import router as auth_router
from app.features.auth.service import attempts
from app.features.chats.router import router as chats_router
from app.features.connections.router import router as connections_router
from app.features.content.router import router as content_router
from app.features.github.router import router as github_router
from app.features.knowledge.router import router as knowledge_router
from app.features.planning.router import router as planning_router
from app.features.proposals.router import router as proposals_router
from app.features.system.router import router as system_router
from app.integrations.github.client import GitHubError
from app.integrations.crm.client import CrmError
from app.features.crm.router import router as crm_router

app = FastAPI(
    title="Work Agent",
    version="0.2.0",
    docs_url=None,
    openapi_url="/api/v1/openapi.json",
    redoc_url=None,
)


@app.exception_handler(graph.GraphError)
async def graph_error(request, exc):
    return JSONResponse(
        {"detail": str(exc)},
        status_code=exc.status if exc.status in {401, 403, 404, 409, 429} else 502,
    )


@app.exception_handler(ValueError)
async def value_error(request, exc):
    return JSONResponse({"detail": str(exc)[:1000]}, status_code=400)


@app.middleware("http")
async def headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(auth_router)
app.include_router(connections_router)
app.include_router(content_router)
app.include_router(knowledge_router)
app.include_router(chats_router)
app.include_router(proposals_router)
app.include_router(system_router)
app.include_router(github_router)
app.include_router(planning_router)
app.include_router(crm_router)


@app.exception_handler(CrmError)
async def crm_error(request, exc):
    return JSONResponse(
        {"detail": str(exc)},
        status_code=exc.status if exc.status in {400, 401, 403, 404, 409, 429} else 502,
    )


@app.exception_handler(GitHubError)
async def github_error(request, exc):
    return JSONResponse(
        {"detail": str(exc)},
        status_code=exc.status if exc.status in {401, 403, 404, 429} else 502,
    )
