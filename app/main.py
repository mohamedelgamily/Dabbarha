from fastapi import FastAPI

from app.api.routes.auth import router as auth_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.forecast import router as forecast_router
from app.api.routes.obligations import router as obligations_router

app = FastAPI(title="Dabbarha API")

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(obligations_router, prefix="/obligations", tags=["obligations"])
app.include_router(forecast_router, prefix="/forecast", tags=["forecast"])
app.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
