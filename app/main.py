"""FastAPI application factory for the Professor Carvalho Pokémon assistant."""

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import admin, chat, health, history
from app.models.chat import SupportedLanguage


def create_app() -> FastAPI:
    app = FastAPI(
        title="Professor Carvalho — Pokémon Assistant API",
        description=(
            "API conversacional especializada no universo Pokémon, com a "
            "personalidade permanente do Professor Carvalho (Professor Oak)."
        ),
        version="1.0.0",
    )

    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(history.router)
    app.include_router(admin.router)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        for error in exc.errors():
            is_language_field = error.get("loc", [None])[-1] == "language"
            is_invalid_value = error.get("type") != "missing"
            if is_language_field and is_invalid_value:
                return JSONResponse(
                    status_code=422,
                    content={
                        "detail": "Idioma não suportado. / Unsupported language.",
                        "supported_languages": [lang.value for lang in SupportedLanguage],
                    },
                )
        return JSONResponse(
            status_code=422, content={"detail": jsonable_encoder(exc.errors())}
        )

    return app


app = create_app()
