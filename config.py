from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    lexe_client_credentials: str = ""
    consumer_lexe_credentials: str = ""
    fee_rate: float = 0.10
    provider_base_url: str = "http://localhost:8000"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"

settings = Settings()
