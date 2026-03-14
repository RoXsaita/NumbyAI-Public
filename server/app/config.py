"""Configuration management"""
import os
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """Application settings"""

    # Database
    database_url: str = "sqlite:///./finance_recon.db"

    # OAuth (Auth0)
    auth0_domain: Optional[str] = None
    auth0_client_id: Optional[str] = None
    auth0_client_secret: Optional[str] = None
    auth0_audience: Optional[str] = None

    # OAuth (Supabase)
    supabase_url: Optional[str] = None
    supabase_anon_key: Optional[str] = None
    supabase_service_key: Optional[str] = None

    # Server
    server_url: str = "https://your-server.com"
    secret_key: str = Field(default="dev-only-not-for-production")

    # CORS - comma-separated list of allowed origins
    allowed_origins: str = "http://localhost:3000,http://localhost:5173"

    # LLM provider. Supported: "ollama" (default), "minimax".
    llm_provider: Optional[str] = None
    llm_timeout_seconds: int = 300

    # Ollama (local LLM)
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:9b"
    # None => omit `think` option; bool => force thinking on/off.
    ollama_think: Optional[bool] = False
    # None => use Ollama's model default (typically 32768 for qwen3.5:9b).
    ollama_num_ctx: Optional[int] = None

    # MiniMax (cloud LLM — OpenAI-compatible API)
    minimax_api_key: Optional[str] = None
    minimax_base_url: str = "https://api.minimax.io/v1"
    minimax_model: str = "MiniMax-M2.5"

    categorization_batch_size: int = 20
    categorization_max_workers: int = 5
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",  # Ignore extra environment variables
    )
    
    def validate_production_settings(self) -> None:
        """Validate settings for production use. Call during startup."""
        is_production = os.getenv("ENVIRONMENT", "").lower() == "production"
        if is_production and "dev-only" in self.secret_key.lower():
            raise ValueError(
                "SECRET_KEY must be set to a secure value in production. "
                "Set the SECRET_KEY environment variable."
            )


settings = Settings()
