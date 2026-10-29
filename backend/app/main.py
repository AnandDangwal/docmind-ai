from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.chat import router as chat_router
from app.assistant.agent import build_agent
from app.auth.router import router as auth_router
from app.config import settings
from app.database.session import AsyncSessionLocal
from app.retrieval.embeddings import GeminiQueryEmbedder
from app.retrieval.retriever import DocumentRetriever


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.document_agent = build_agent(settings)
    app.state.document_retriever = DocumentRetriever(
        AsyncSessionLocal, GeminiQueryEmbedder()
    )
    yield


app = FastAPI(lifespan=lifespan)


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    # A handled response passes through CORS, unlike an unhandled server error.
    structlog.get_logger(__name__).error(
        "database.request_failed", path=request.url.path, error_type=type(exc).__name__
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "The database request failed. Please try again shortly."},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(chat_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", reload=True)
