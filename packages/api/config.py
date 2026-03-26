"""API runtime settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed settings for the API package."""

    rhumb_env: str = "development"
    rhumb_api_host: str = "0.0.0.0"
    rhumb_api_port: int = 8000
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:54322/postgres"
    redis_url: str = "redis://localhost:6379/0"
    supabase_url: str = "http://localhost:54321"
    supabase_service_role_key: str = "replace-me"

    rhumb_admin_secret: str | None = None

    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None

    # OAuth providers
    github_client_id: str | None = None
    github_client_secret: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None

    # Auth
    auth_jwt_secret: str | None = None  # Falls back to rhumb_admin_secret if unset
    auth_frontend_url: str = "https://rhumb.dev"
    auth_api_url: str = "https://api.rhumb.dev"  # Where OAuth callbacks land

    # Billing bootstrap
    billing_bootstrap_starter_credits_cents: int = 100

    anthropic_api_key: str | None = None
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_model: str = "claude-3-5-sonnet-latest"
    score_explanation_max_chars: int = 150

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
