import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dabbarha.db")

JWT_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY",
    "development-only-insecure-jwt-secret-change-me",
)
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
