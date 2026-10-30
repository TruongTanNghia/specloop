"""Cấu hình ứng dụng, đọc từ biến môi trường / tệp .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPO_ROOT / ".env"), ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    APP_NAME: str = "SpecLoop"
    DATABASE_URL: str = f"sqlite:///{(REPO_ROOT / 'data' / 'specloop.db').as_posix()}"
    SECRET_KEY: str = "dev-secret-change-me"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"
    BENCH_DIR: str = str(REPO_ROOT / "SpecLoop-Bench")
    DATA_DIR: str = str(REPO_ROOT / "data")

    # LLM (một adapter OpenAI-compatible: OpenAI, Gemini, Ollama, LM Studio)
    LLM_BASE_URL: str = ""
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""
    LLM_MAX_CONCURRENCY: int = 4
    LLM_CACHE_ENABLED: bool = True
    LLM_TIMEOUT_S: float = 120.0
    LLM_JSON_MODE: bool = True

    # Kiểm thử
    TEST_ALLOWED_NETWORKS: str = "127.0.0.0/8,::1/128,172.16.0.0/12,192.168.0.0/16,10.0.0.0/8"
    TEST_SANDBOX_MAX_RPS: float = 5.0
    TEST_PUBLIC_MAX_RPS: float = 1.0
    TEST_SANDBOX_BUDGET: int = 150
    TEST_PUBLIC_BUDGET: int = 30
    TEST_TIMEOUT_S: float = 10.0

    JOB_WORKERS: int = 4

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_networks(self) -> list[str]:
        return [n.strip() for n in self.TEST_ALLOWED_NETWORKS.split(",") if n.strip()]

    @property
    def llm_configured(self) -> bool:
        return bool(self.LLM_BASE_URL and self.LLM_MODEL)


@lru_cache
def get_settings() -> Settings:
    return Settings()
