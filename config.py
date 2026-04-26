from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    lexe_client_credentials: str = ""
    consumer_lexe_credentials: str = ""
    anthropic_api_key: str = ""
    fee_rate: float = 0.10
    provider_base_url: str = "http://localhost:8000"

    # Tier thresholds
    bronze_ceiling: int = 150
    silver_ceiling: int = 400
    silver_min_score: float = 70.0
    silver_min_calls: int = 10
    gold_min_score: float = 85.0
    gold_min_calls: int = 25

settings = Settings()
