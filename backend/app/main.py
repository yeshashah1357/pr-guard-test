import logging

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import auth, findings, repos, webhooks

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="PR Guard", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Authorization", "Content-Type"],
    )

    api = APIRouter(prefix="/api")
    for module in (auth, repos, findings, webhooks):
        api.include_router(module.router)

    @api.get("/health", tags=["health"])
    def health() -> dict:
        return {"status": "ok"}

    app.include_router(api)
    return app


app = create_app()
