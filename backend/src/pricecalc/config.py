from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "pricecalc"
    debug: bool = False

    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # Vite dev server. Add deployed origins here rather than widening to "*".
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Seed for the simulated market-data feed; fixed so runs are reproducible.
    sim_seed: int = 42


settings = Settings()
