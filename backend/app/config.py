"""
Application configuration.

Every field name here must match DATA_CONTRACT.md §1 "Environment & Config Contract"
exactly — that file is authoritative and binding. If you need a new env var, add it
there first, then here.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    ENVIRONMENT: str = "development"
    SECRET_KEY: str = "dev-secret-change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # --- Postgres ---
    POSTGRES_USER: str = "cascadence"
    POSTGRES_PASSWORD: str = "cascadence"
    POSTGRES_DB: str = "cascadence"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432

    # --- Neo4j ---
    NEO4J_URI: str = "bolt://neo4j:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "neo4j"

    # --- Redis / Celery ---
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"

    # --- External data sources ---
    SEC_EDGAR_USER_AGENT: str = "Cascadence dev dev@example.com"
    NEWS_API_KEY: str | None = None
    COPERNICUS_CLIENT_ID: str | None = None
    COPERNICUS_CLIENT_SECRET: str | None = None
    ANTHROPIC_API_KEY: str | None = None

    # --- Alerting dispatch ---
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SLACK_WEBHOOK_URL: str | None = None

    MODEL_ARTIFACT_DIR: str = "../ml/training/artifacts"

    INGESTION_CACHE_DIR: str = "../data/cache"
    NLP_CACHE_DIR: str = "../ml/nlp_cache"
    NLP_SPACY_MODEL: str = "en_core_web_lg"
    NLP_EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    INGESTION_TICKERS: str = ""
    INGESTION_INTERVAL_SECONDS: int = 21600

    PHASE3_CACHE_DIR: str = "../data/phase3_cache"
    PHASE3_INPUT_DIR: str = "../data/phase3_inputs"
    EARTHDATA_TOKEN: str | None = None
    PHASE3_LOCATIONS: str = ""
    PHASE3_INTERVAL_SECONDS: int = 86400

    # --- Observability ---
    PROMETHEUS_ENABLED: bool = True

    @property
    def sqlalchemy_database_uri(self) -> str:
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
