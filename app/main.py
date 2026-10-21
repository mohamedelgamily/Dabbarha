from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from starlette.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import API_DOCS_ENABLED, SETTINGS
from app.core.api_security_settings import APISecuritySettings
from app.core.api_security import SecurityRuntime
from app.core.rate_limit import StoreUnavailable
from app.core.request_security import RequestSecurityMiddleware

from app.api.routes.affordability import router as affordability_router
from app.api.routes.auth import router as auth_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.forecast import router as forecast_router
from app.api.routes.obligations import router as obligations_router


@asynccontextmanager
async def lifespan(application):
    try:
        await run_in_threadpool(application.state.security.limiter.store.ping)
    except StoreUnavailable:
        raise RuntimeError("Shared request protection is unavailable; startup refused.") from None
    try:
        yield
    finally:
        await run_in_threadpool(application.state.security.limiter.store.close)


app = FastAPI(
    lifespan=lifespan,
    title="Dabbarha API",
    debug=False,
    docs_url="/docs" if API_DOCS_ENABLED else None,
    redoc_url="/redoc" if API_DOCS_ENABLED else None,
    openapi_url="/openapi.json" if API_DOCS_ENABLED else None,
)

app.state.security = SecurityRuntime(APISecuritySettings.from_environ(SETTINGS.app_env))
app.add_middleware(RequestSecurityMiddleware)


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Echoing input can disclose credentials and cannot serialize NaN/Infinity.
    # Keep the standard detail/type/loc/msg contract consumed by the mobile client.
    errors = [
        {key: error[key] for key in ("type", "loc", "msg")}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    # Never return SQL, parameters, driver messages or stack traces to clients.
    if isinstance(exc, IntegrityError):
        return JSONResponse(
            status_code=409,
            content={"detail": "The change conflicts with stored data. Please review your request."},
        )
    return JSONResponse(
        status_code=500,
        content={"detail": "The database operation could not be completed. Please try again."},
    )


app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(obligations_router, prefix="/obligations", tags=["obligations"])
app.include_router(forecast_router, prefix="/forecast", tags=["forecast"])
app.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
app.include_router(affordability_router, prefix="/affordability", tags=["affordability"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
