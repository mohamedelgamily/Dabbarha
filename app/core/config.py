import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dabbarha.db")

JWT_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY",
    "development-only-insecure-jwt-secret-change-me",
)
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.7-flash")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

RAG_ENABLED = os.getenv("RAG_ENABLED", "true").lower() in {"1", "true", "yes"}
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))
RAG_CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "500"))
RAG_CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "50"))
RAG_SCORE_THRESHOLD = float(os.getenv("RAG_SCORE_THRESHOLD", "0.1"))
