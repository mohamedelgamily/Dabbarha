from fastapi import FastAPI

from app.api.routes.auth import router as auth_router

app = FastAPI(title="Dabbarha API")

app.include_router(auth_router, prefix="/auth", tags=["auth"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
